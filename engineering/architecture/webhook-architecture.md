# Webhook Architecture

Webhooks are HTTP callbacks that enable real-time communication between services. They're essential for building reactive systems where one service needs to notify another of events without polling.

## Core Components

A robust webhook system requires several key architectural elements:

```python
# Basic webhook receiver structure
from flask import Flask, request, jsonify
import hashlib
import hmac
import time
import json
from typing import Dict, Any

app = Flask(__name__)

class WebhookHandler:
    def __init__(self):
        self.secret = "your-webhook-secret"
        self.retry_attempts = 3
        self.max_backoff = 60

    def verify_signature(self, payload: bytes, signature: str) -> bool:
        expected = hmac.new(
            self.secret.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(signature, f"sha256={expected}")

    def handle_webhook(self, event_data: Dict[str, Any]) -> bool:
        # Process webhook logic here
        try:
            # Your business logic
            result = process_event(event_data)
            return True
        except Exception as e:
            # Log error and return failure
            return False
```

## Reliable Delivery

Reliable delivery ensures events aren't lost during transmission. The most common approach is to implement an acknowledgment system:

```python
@app.route('/webhook', methods=['POST'])
def webhook_endpoint():
    payload = request.get_data()
    signature = request.headers.get('X-Hub-Signature-256')

    # Verify signature first
    if not verify_signature(payload, signature):
        return jsonify({"error": "Invalid signature"}), 401

    # Acknowledge receipt immediately
    response = jsonify({"status": "received"})

    # Process in background
    process_webhook.delay(payload)

    return response, 200
```

## Retry with Backoff

Network failures are inevitable. Implement exponential backoff to handle transient issues gracefully:

```python
import time
import random
from functools import wraps

def retry_with_backoff(max_retries=3, base_delay=1, max_delay=60):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise e

                    # Exponential backoff with jitter
                    delay = min(base_delay * (2 ** attempt), max_delay)
                    delay += random.uniform(0, 1)  # Add jitter
                    time.sleep(delay)
            return None
        return wrapper
    return decorator

@retry_with_backoff(max_retries=3, base_delay=1)
def send_webhook(url: str, payload: dict):
    response = requests.post(url, json=payload, timeout=30)
    response.raise_for_status()
    return response
```

## Signature Verification

Always verify webhook signatures to prevent unauthorized access:

```python
def verify_github_signature(payload: bytes, signature: str) -> bool:
    """Verify GitHub webhook signature"""
    secret = <redacted-secret>'WEBHOOK_SECRET')
    if not secret:
        raise ValueError("WEBHOOK_SECRET not configured")

    expected = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()

    # Compare with prefix "sha256="
    return hmac.compare_digest(signature, f"sha256={expected}")

def verify_slack_signature(payload: bytes, timestamp: str, signature: str) -> bool:
    """Verify Slack webhook signature"""
    slack_signing_secret = os.environ.get('SLACK_SIGNING_SECRET')

    # Create bas
