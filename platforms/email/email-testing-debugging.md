# Email Testing and Debugging

## Symptom

Email delivery issues are common in web applications, often manifesting as emails not reaching recipients, being marked as spam, or failing DKIM/SPF verification. Developers frequently encounter situations where emails work perfectly in development but fail in production, or where legitimate emails get filtered by spam filters.

## Gotchas

- **Local testing limitations**: Development environments often lack proper email server configuration
- **Spam filter sensitivity**: Modern spam filters are aggressive and may reject valid emails
- **DNS record confusion**: DKIM and SPF records must be correctly configured for email authentication
- **Client rendering differences**: Email clients render HTML differently, causing layout issues
- **Authentication failures**: Missing or incorrect DMARC policies can cause delivery rejection

## Tools and Techniques

### Mailtrap Integration

Mailtrap provides a sandbox environment for testing emails without sending them to real recipients:

```python
import smtplib
from email.mime.text import MIMEText

# Configure Mailtrap SMTP
smtp_server = "smtp.mailtrap.io"
smtp_port = 2525
username = "your_mailtrap_username"
password = "your_mailtrap_password"

def send_test_email(to_email, subject, body):
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['To'] = to_email
    msg['From'] = "sender@example.com"

    server = smtplib.SMTP(smtp_server, smtp_port)
    server.starttls()
    server.login(username, password)
    server.send_message(msg)
    server.quit()
```

### Ethereal Email Testing

Ethereal provides temporary email accounts for testing:

```javascript
const nodemailer = require('nodemailer');

// Configure Ethereal SMTP
const transporter = nodemailer.createTransporter({
  host: 'smtp.ethereal.email',
  port: 587,
  secure: false,
  auth: {
    user: 'testuser@ethereal.email',
    pass: 'testpassword'
  }
});

async function sendTestEmail() {
  const info = await transporter.sendMail({
    from: '"Test Sender" <sender@example.com>',
    to: 'recipient@example.com',
    subject: 'Test Email',
    text: 'This is a test email',
    html: '<b>This is a test email</b>'
  });

  console.log('Preview URL:', nodemailer.getTestMessageUrl(info));
}
```

###
