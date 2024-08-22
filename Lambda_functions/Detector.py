import json
import boto3
import cv2
import numpy as np
import os
import logging
import time

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3 = boto3.client('s3')
dynamodb = boto3.client('dynamodb')

LOCAL_CONFIG_FILE = '/tmp/yolov3-tiny.cfg'
LOCAL_WEIGHTS_FILE = '/tmp/yolov3-tiny.weights'
LOCAL_NAMES_FILE = '/tmp/coco.names'

MODEL_BUCKET = 'tuw-dic-ex3'
MODEL_PREFIX = 'model/'
DYNAMO_TABLE_NAME = 'Detections'

net = None
classes = None

def download_model_files():
    try:
        if not os.path.exists(LOCAL_CONFIG_FILE):
            logger.info(f"Downloading {MODEL_PREFIX + 'yolov3-tiny.cfg'} to {LOCAL_CONFIG_FILE}")
            s3.download_file(MODEL_BUCKET, MODEL_PREFIX + 'yolov3-tiny.cfg', LOCAL_CONFIG_FILE)
        if not os.path.exists(LOCAL_WEIGHTS_FILE):
            logger.info(f"Downloading {MODEL_PREFIX + 'yolov3-tiny.weights'} to {LOCAL_WEIGHTS_FILE}")
            s3.download_file(MODEL_BUCKET, MODEL_PREFIX + 'yolov3-tiny.weights', LOCAL_WEIGHTS_FILE)
        if not os.path.exists(LOCAL_NAMES_FILE):
            logger.info(f"Downloading {MODEL_PREFIX + 'coco.names'} to {LOCAL_NAMES_FILE}")
            s3.download_file(MODEL_BUCKET, MODEL_PREFIX + 'coco.names', LOCAL_NAMES_FILE)
    except Exception as e:
        logger.error(f"Error downloading model files: {e}", exc_info=True)
        raise

def load_yolo_model():
    global net, classes
    try:
        if net is None or classes is None:
            logger.info("Loading YOLO model")
            net = cv2.dnn.readNet(LOCAL_WEIGHTS_FILE, LOCAL_CONFIG_FILE)
            with open(LOCAL_NAMES_FILE, 'r') as f:
                classes = [line.strip() for line in f.readlines()]
    except Exception as e:
        logger.error(f"Error loading YOLO model: {e}", exc_info=True)
        raise

def detect_objects(image):
    try:
        height, width, channels = image.shape
        blob = cv2.dnn.blobFromImage(image, 0.00392, (416, 416), (0, 0, 0), True, crop=False)
        net.setInput(blob)
        outs = net.forward(net.getUnconnectedOutLayersNames())

        class_ids = []
        confidences = []
        boxes = []

        for out in outs:
            for detection in out:
                scores = detection[5:]
                class_id = np.argmax(scores)
                confidence = scores[class_id]
                if confidence > 0.5:  # Confidence threshold
                    center_x = int(detection[0] * width)
                    center_y = int(detection[1] * height)
                    w = int(detection[2] * width)
                    h = int(detection[3] * height)
                    x = int(center_x - w / 2)
                    y = int(center_y - h / 2)
                    boxes.append([x, y, w, h])
                    confidences.append(float(confidence))
                    class_ids.append(class_id)

        # Non-Max Suppression
        indices = cv2.dnn.NMSBoxes(boxes, confidences, 0.5, 0.4)
        results = []
        if len(indices) > 0:
            for i in indices.flatten():
                results.append({
                    'label': classes[class_ids[i]],
                    'accuracy': round(confidences[i], 3)
                })

        return results
    except Exception as e:
        logger.error(f"Error in object detection: {e}", exc_info=True)
        raise

def save_to_dynamodb(s3_url, results, inference_time):
    try:
        dynamodb.put_item(
            TableName=DYNAMO_TABLE_NAME,
            Item={
                'S3 URL': {'S': s3_url},
                'Detections': {'S': json.dumps(results)},
                'InferenceTime [ms]': {'N': str(inference_time)}
            }
        )
    except Exception as e:
        logger.error(f"Error saving to DynamoDB: {e}", exc_info=True)
        raise

def lambda_handler(event, context):
    global net, classes
    try:
        logger.info("Received event: %s", json.dumps(event))

        body = event.get('body')
        if isinstance(body, str):
            body = json.loads(body)

        logger.info("Body type: %s", type(body))

        if not body:
            logger.error("Body is empty or None: %s", json.dumps(event))
            raise ValueError("Body is empty or None")

        bucket = body.get('bucket')
        key = body.get('key')  # Get the key from the request body

        if not key:
            raise ValueError("No key provided in the request body")

        s3_url = f's3://{bucket}/{key}'
        download_path = '/tmp/{}'.format(os.path.basename(key))
        
        logger.info("Downloading file from S3: %s", s3_url)
        s3.download_file(bucket, key, download_path)

        logger.info("Loading image with OpenCV from path: %s", download_path)
        image = cv2.imread(download_path)
        if image is None:
            raise ValueError("Error loading image with OpenCV")

        # Ensure model files are downloaded
        logger.info("Downloading model files")
        download_model_files()

        # Load YOLO model if not already loaded
        # The model is loaded once per container lifetime to avoid continuous reloads
        logger.info("Loading YOLO model")
        load_yolo_model()

        start_time = time.time()
        logger.info("Running object detection")
        results = detect_objects(image)
        end_time = time.time()
        inference_time = (end_time - start_time) * 1000  # Convert to milliseconds

        logger.info("Saving results to DynamoDB")
        save_to_dynamodb(s3_url, results, inference_time)

        response_body = {
            's3_url': s3_url,
            'objects': results
        }

        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Allow-Methods': 'OPTIONS,POST,GET'
            },
            'body': json.dumps(response_body)
        }
    except Exception as e:
        logger.error(f"Error processing file: {e}", exc_info=True)
        return {
            'statusCode': 500,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Allow-Methods': 'OPTIONS,POST,GET'
            },
            'body': json.dumps({'error': str(e)})
        }
