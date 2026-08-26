# GitHub Webhook Signature Verification

## Overview

GitHub webhooks provide a secure way to receive notifications about events happening in your repositories. However, to ensure these notifications are legitimate and not forged, you must verify their signatures using HMAC-SHA256 hashing. This article explains how to implement proper webhook signature verification in your applications.

## Symptom

When implementing GitHub webhooks without proper signature verification, you'll encounter several issues:
- Unauthorized requests can trigger your application logic
- Malicious actors can forge webhook events
- Your application may process fake notifications
- Security vulnerabilities in production environments

## Gotchas

Several common pitfalls exist when implementing webhook verification:
- Using the wrong secret key or endpoint
- Not validating timestamps to prevent replay attacks
- Incorrect HMAC implementation with wrong algorithm
- Missing proper error handling and logging
- Forgetting to validate the X-Hub-Signature-256 header format

## Implementation

### Required Headers

GitHub webhooks include the `X-Hub-Signature-256` header containing the HMAC signature. The header format is: `sha256=signature_value`

### Fastify Middleware Example

```javascript
const fastify = require('fastify')({ logger: true });
const crypto = require('crypto');

const WEBHOOK_SECRET = process.env.WEBHOOK_SECRET;

const verifyGitHubSignature = (request, reply) => {
  const signature = request.headers['x-hub-signature-256'];
  const payload = request.body;

  if (!signature) {
    return reply.code(401).send('Missing signature');
  }

  const expectedSignature = 'sha256=' +
    crypto.createHmac('sha256', WEBHOOK_SECRET)
      .update(JSON.stringify(payload))
      .digest('hex');

  if (!crypto.timingSafeEqual(
    Buffer.from(signature),
    Buffer.from(expectedSignature)
  )) {
    return reply.code(401).send('Invalid signature');
  }

  return true;
};

fastify.post('/webhook', {
  preHandler: verifyGitHubSignature
}, async (request, reply) => {
  // Process webhook event
  console.log('Received valid webhook:', request.body.action);
  return reply.send({ status: 'success' });
});
```

### Express Middleware Example

```javascript
const express = require('express');
const crypto = require('crypto');

const app = express();
app.use(express.json());

const WEBHOOK_SECRET = process.env.WEBHOOK_SECRET;

const verifySignature = (req, res, next) => {
  const signature = req.headers['x-hub-signature-256'];
  const payload = JSON.stringify(req.body);

  if (!signature) {
    return res.status(401).send('Missing signature');
  }

  const expectedSignature = 'sha256=' +
    crypto.createHmac
