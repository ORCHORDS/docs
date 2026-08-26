# Transactional Email Best Practices

Transactional emails are critical for user engagement and business success. Following best practices ensures your messages reach inboxes and provide optimal user experience.

## Template Structure

A well-structured email template follows a logical flow with clear sections. Use semantic HTML elements and maintain consistent spacing.

```html
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Transaction Confirmation</title>
</head>
<body>
    <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
            <td align="center">
                <table width="600" cellpadding="0" cellspacing="0">
                    <tr>
                        <td>
                            <h1>Order Confirmation</h1>
                            <p>Thank you for your purchase!</p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
```

## Inline CSS

Most email clients strip external stylesheets. Always use inline CSS for maximum compatibility.

```html
<style>
    /* This will be stripped */
    .header { font-size: 24px; color: #333; }
</style>

<!-- Convert to inline -->
<h1 style="font-size: 24px; color: #333;">Order Confirmation</h1>
```

## Plain Text Alternative

Always include a plain text version for users who prefer it or have email clients that don't support HTML.

```html
<!-- HTML version -->
<div class="content">Thank you for your order!</div>

<!-- Plain text alternative -->
<div style="display: none; font-size: 1px; color: #ffffff;">
    Thank you for your order!
</div>
```

## Unsubscribe Headers

Include proper unsubscribe functionality and headers to comply with anti-spam laws.

```html
<!-- Unsubscribe link -->
<a >Unsubscribe from this list</a>

<!-- Email headers -->
X-MSMail-Priority: Normal
X-Mailer: Transactional Email System
Precedence: bulk
```

## Bounce/Complaint Handling

Implement robust error handling to maintain sender reputation and deliverability.

```javascript
// Example bounce handling
const handleBounce = (email, reason) => {
    if (reason.includes('hard')) {
        // Remove from mailing list
