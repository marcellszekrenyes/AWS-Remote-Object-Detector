let postData = null;
const bucketName = 'tuw-dic-ex3'; // S3 bucket name
let timerInterval; // Variable to hold the interval ID for the timer
let startTime; // Variable to hold the start time of the upload

// Function to fetch the pre-signed URL for uploading images to S3
async function fetchPostData() {
  try {
    const response = await fetch('https://8cjmfbdlwc.execute-api.us-east-1.amazonaws.com/prod');
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    const data = await response.json();
    console.log('Fetched postData:', data);

    return data.body ? JSON.parse(data.body) : data;
  } catch (error) {
    console.error('Error fetching pre-signed data:', error);
    throw error;
  }
}

// Function to handle file upload and detection
async function handleFileUpload(file) {
  try {
    const postData = await fetchPostData();

    if (!postData || !postData.fields) {
      throw new Error('Error fetching pre-signed data. Please try again later.');
    }

    const formData = new FormData();
    for (const [key, value] of Object.entries(postData.fields)) {
      formData.append(key, value);
    }
    formData.append('file', file);

    const s3Response = await fetch(postData.url, {
      method: 'POST',
      body: formData
    });

    const responseText = await s3Response.text();

    if (!s3Response.ok) {
      throw new Error(`HTTP error! status: ${s3Response.status} response: ${responseText}`);
    }

    const requestBody = {
      bucket: bucketName,
      key: postData.fields.key,
      fileName: file.name
    };

    const detectResponse = await fetch('https://f3fh4ib1wd.execute-api.us-east-1.amazonaws.com/prod/detect', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(requestBody)
    });

    const detectResponseText = await detectResponse.text();

    if (!detectResponse.ok) {
      throw new Error(`HTTP error! status: ${detectResponse.status} response: ${detectResponseText}`);
    }

    // Parse the response from the detection API
    const detectData = JSON.parse(detectResponseText);
    console.log('Detection results:', detectData);

    if (detectData.error) {
      throw new Error(detectData.error);
    }

    // Extract nested body if it exists
    let responseBody = detectData.body;
    if (typeof responseBody === 'string') {
      responseBody = JSON.parse(responseBody);
    } else if (responseBody.body) {
      responseBody = JSON.parse(responseBody.body);
    }

    const s3Url = responseBody.s3_url;
    const objects = responseBody.objects.map(obj => `label: ${obj.label}, accuracy: ${obj.accuracy.toFixed(3)}`).join(", ");

    const detectionHtml = `<div class="detection-item"><p>Detections for ${file.name}:<br>S3 URL: ${s3Url}<br>Objects: [${objects}]</p></div>`;
    document.getElementById('uploadStatus').innerHTML += detectionHtml;

  } catch (error) {
    console.error('Error uploading file or fetching detection results:', error);
    document.getElementById('uploadStatus').innerHTML += `<p>Error uploading ${file.name}: ${error.message}</p>`;
  }
}

// Function to start the timer
function startTimer() {
  startTime = Date.now();
  timerInterval = setInterval(() => {
    const elapsedTime = (Date.now() - startTime) / 1000;
    document.getElementById('timer').textContent = `Time: ${elapsedTime.toFixed(3)}s`;
  }, 10);
}

// Function to stop the timer
function stopTimer() {
  clearInterval(timerInterval);
  const elapsedTime = (Date.now() - startTime) / 1000;
  document.getElementById('timer').textContent = `Total Time: ${elapsedTime.toFixed(3)}s`;
}

// Fetch the pre-signed URL when the page loads
document.addEventListener('DOMContentLoaded', async () => {
  try {
    postData = await fetchPostData();
  } catch (error) {
    console.error('Error during fetchPostData execution:', error);
  }
});

// Event listener to update file count when files are selected
document.getElementById('fileInput').addEventListener('change', () => {
  const files = document.getElementById('fileInput').files;
  const fileCount = document.getElementById('fileCount');
  fileCount.textContent = `Selected files: ${files.length}`;
});

// Event listener for the upload button
document.getElementById('uploadButton').addEventListener('click', async () => {
  startTimer();
  const files = document.getElementById('fileInput').files;
  const uploadStatus = document.getElementById('uploadStatus');
  uploadStatus.style.borderColor = 'orange';

  const uploadPromises = Array.from(files).map(file => handleFileUpload(file));

  await Promise.all(uploadPromises);
  stopTimer();
  uploadStatus.style.borderColor = 'green';
});
