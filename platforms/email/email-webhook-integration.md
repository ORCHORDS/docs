# Email Webhook Integration Patterns

## Overview
Email webhook integration enables real-time notifications for email events like deliveries, bounces, and opens. Proper implementation requires understanding event types, handling delivery status, managing bounces, ensuring idempotent processing, implementing retries, and verifying security.

## Event Types
Email providers send various webhook events:
- **Delivery**: Email successfully delivered to recipient's server
- **Bounce**: Email failed to deliver due to invalid address or server issues
- **Open**: Recipient opened the email
- **Click**: Recipient clicked on links within the email
- **Spam Report**: Recipient marked email as spam
- **Unsubscribe**: Recipient requested to be removed from mailing list

## Delivery Status
Delivery webhooks contain detailed status information:
```json
{
  "event": "delivered",
  "email": "user@example.com",
  "timestamp": "2023-12-01T10:30:00Z",
  "message_id": "msg_12345",
  "provider": "sendgrid"
}
```

## Bounce Webhooks
Bounce handling requires categorizing failures:
```javascript
app.post('/webhook/bounce', (req, res) => {
  const { event, email, reason } = req.body;

  if (event === 'bounce') {
    switch (reason) {
      case 'hard':
        // Remove from mailing list permanently
        break;
      case 'soft':
        // Retry delivery later
        break;
    }
  }
});
```

## Idempotent Processing
Ensure webhook handlers can process the same event multiple times:
```python
import hashlib
import logging

def process_webhook_event(event_data):
    # Create unique identifier for event
    event_hash = hashlib.md5(str(event_data).encode()).hexdigest()

    # Check if already processed
    if redis.exists(f"processed:{event_hash}"):
        logging.info("Event already processed")
        return

    # Process event
    handle_event(event_data)

    # Mark as processed
    redis.setex(f"processed:{event_hash}", 86400, "1")  # 24h expiry
```

## Retry Mechanism
Implement exponential backoff for failed deliveries:
```javascript
const retryWebhook = async (url, payload, retries = 3) =>
