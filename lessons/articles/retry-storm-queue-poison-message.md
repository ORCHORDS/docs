# Retry Storm from Poison Message

## Symptom

A queue consumer enters an infinite retry loop when processing a malformed or problematic message, causing system degradation and resource exhaustion. The consumer continuously attempts to process the same message with exponential backoff, but fails repeatedly, leading to a "retry storm" that overwhelms the system.

## Gotchas

- **Infinite Retry Loops**: Messages that consistently fail cause consumers to retry indefinitely without proper termination conditions
- **Resource Exhaustion**: Continuous retries consume CPU, memory, and network resources, potentially crashing the system
- **DLQ Bypass Issues**: Poor DLQ configuration can lead to messages being reprocessed multiple times before reaching dead letter queue
- **Exponential Backoff Misconfiguration**: Incorrect backoff parameters can either retry too quickly or too slowly, exacerbating the problem
- **Poison Message Detection Failure**: Without proper detection mechanisms, bad messages continue to cause system issues

## Practical Solution

Implement a comprehensive poison message handling strategy with these key components:

```python
# Example implementation
import time
import logging
from typing import Optional

class PoisonMessageHandler:
    def __init__(self):
        self.retry_count = 0
        self.max_retries = 3
        self.dlq_queue = "dead_letter_queue"
        self.circuit_breaker = CircuitBreaker()

    def process_message(self, message: dict) -> bool:
        try:
            # Attempt to process message
            result = self._process_with_retry(message)
            return True
        except Exception as e:
            self.retry_count += 1

            # Check circuit breaker
            if not self.circuit_breaker.allow_request():
                logging.warning("Circuit breaker tripped, rejecting message")
                return False

            # Check retry limit
            if self.retry_count > self.max_retries:
                self._move_to_dlQ(message)
                return False

            # Apply exponential backoff
            delay = 2 ** self.retry_count
            time.sleep(delay)
            return self.process_message(message)  # Recursive retry

    def _move_to_DLQ(self, message: dict):
        """Move poison message to dead letter queue"""
        # Send to DLQ with metadata about failure
        logging.error(f"Moving poison message to DLQ: {message}")
        # Implementation details here
```

## Key Components

**Queue Consumer Retry Loop**: Implement bounded retry logic with exponential backoff to
