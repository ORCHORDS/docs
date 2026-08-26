# Web Workers for CPU-Heavy Tasks

Web Workers enable JavaScript to run computationally intensive tasks without blocking the main UI thread, making them essential for maintaining responsive applications.

## What are Web Workers?

Web Workers are background threads that execute JavaScript code independently of the main execution thread. They're perfect for CPU-heavy operations like data processing, cryptographic calculations, and image manipulation.

```javascript
// Creating a worker
const worker = new Worker('worker.js');

// Sending data to worker
worker.postMessage({ data: largeArray });

// Receiving results
worker.onmessage = function(e) {
    console.log('Results:', e.data);
};
```

## Offloading Parsing Operations

Parsing large JSON datasets or XML documents can freeze the UI. Workers handle this efficiently:

```javascript
// In main thread
const worker = new Worker('parser-worker.js');
worker.postMessage({ type: 'JSON_PARSE', data: jsonString });
worker.onmessage = (e) => {
    const parsedData = e.data.result;
};

// In parser-worker.js
self.onmessage = function(e) {
    if (e.data.type === 'JSON_PARSE') {
        const result = JSON.parse(e.data.data);
        self.postMessage({ result });
    }
};
```

## Cryptographic Operations

Heavy crypto computations like hashing, encryption, or key derivation benefit from worker isolation:

```javascript
// Main thread
const cryptoWorker = new Worker('crypto-worker.js');
cryptoWorker.postMessage({
    type: 'SHA256',
    data: 'secret-message'
});

cryptoWorker.onmessage = (e) => {
    console.log('Hash:', e.data.hash);
};

// In crypto-worker.js
self.onmessage = async function(e) {
    if (e.data.type === 'SHA256') {
        const hashBuffer = await crypto.subtle.digest(
            'SHA-256',
            new TextEncoder().encode(e.data.data)
        );
        const hashArray = Array.from(new Uint8Array(hashBuffer));
        const hashHex = hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
        self.postMessage({ hash: hashHex });
    }
};
```

## Image Processing

Complex image manipulation operations like filters, resizing, or canvas transformations should run in workers:

```javascript
// Main thread
const imageWorker = new Worker('image-worker.js');
imageWorker.postMessage({
    type: 'resize',
    imageData: imageCanvas,
    width: 200,
    height: 200
});

imageWorker.onmessage = (e) => {
    const processedImage = e.data.result;
};

// In image-worker.js
self.onmessage = function(e) {
    if (e.data.type === 'resize') {
        // Process image data here
        const result = resizeImage(e.data.imageData, e.data.width, e.data.height);
        self.postMessage({ result });
    }
