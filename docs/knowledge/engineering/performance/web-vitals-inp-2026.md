# web-vitals-inp-2026

## What is Interaction to Next Paint (INP)?

Interaction to Next Paint (INP) measures the responsiveness of a web page by tracking the time between a user interaction and when the browser renders the visual feedback. This metric focuses on the perceived performance during user actions like clicks, taps, or keypresses.

INP became a Core Web Vitals metric in 2024, replacing First Input Delay (FID) as the primary measure of interactivity. The target threshold is 200ms for good performance, meaning interactions should complete within 200ms of user input.

```javascript
// INP measurement example
const observer = new PerformanceObserver((list) => {
  for (const entry of list.getEntries()) {
    console.log('INP:', entry.startTime);
  }
});
observer.observe({entryTypes: ['first-input']});
```

## Responsive Interactions

Responsive interactions are crucial for good INP scores. Users expect immediate visual feedback when interacting with elements. This includes button clicks, form submissions, navigation, and any interactive components.

```javascript
// Optimized click handler
document.getElementById('submit-btn').addEventListener('click', async (e) => {
  e.preventDefault();

  // Show immediate visual feedback
  const button = e.target;
  button.disabled = true;
  button.textContent = 'Processing...';

  try {
    await submitForm();
    // Handle success
  } finally {
    // Reset button state
    button.disabled = false;
    button.textContent = 'Submit';
  }
});
```

## Long Tasks and Main Thread Blocking

Long tasks (>50ms) significantly impact INP by blocking the main thread. These tasks prevent the browser from responding to user interactions, causing delays in visual feedback.

```javascript
// Bad: Long task blocking main thread
function heavyCalculation() {
  let sum = 0;
  for (let i = 0; i < 1000000000; i++) {
    sum += Math.sqrt(i);
  }
  return sum;
}

// Good: Split into smaller tasks using requestIdleCallback
function processInChunks(data, chunkSize = 1000) {
  let index = 0;

  function processChunk() {
    const endIndex = Math.min(index + chunkSize, data.length);

    for (let i = index; i < endIndex; i++) {
      // Process data[i]
    }

    index = endIndex;

    if (index < data.length) {
      requestIdleCallback(processChunk);
    }
  }

  processChunk();
}
```

## Yield to Main Thread

Yielding to the main thread ensures responsive interactions by allowing the browser to process user input between long-running operations. This can be achieved through:

- `requestIdleCallback()` for background tasks
- `setTimeout
