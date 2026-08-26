# log-injection-prevention

**Issue:** Log injection (CRLF in user input corrupting logs)
**Date:** 2026-08-09
**Status:** documented

## Symptom
A user submits a name like `Alice\n[ERROR] Database connection
lost\n`. The log file now contains a fake error line.
A log-monitor alert fires. The on-call is paged for a
nonexistent issue. Time wasted: 30 minutes.

## Root cause
**Log injection** is when user-controlled input is included in
log lines without sanitization. An attacker injects newline
characters to create fake log entries.

**Source:** OWASP — Log Injection:
https://owasp.org/www-community/attacks/Log_Injection

> "Log injection attacks ... allow an attacker to forge log
> entries, inject malicious content into logs, or even
> truncate log entries."

## The attack

```ts
// Vulnerable code
function logUserAction(userId: string, action: string) {
  console.log(`User ${userId} performed action ${action}`);
}

// Attacker controls `action` via a form field
logUserAction('u_123', 'login\n[ERROR] Database connection lost\n');
// Log file now has:
// User u_123 performed action login
// [ERROR] Database connection lost
//
// A log-monitor that scans for "[ERROR]" fires an alert.
```

## Fix

### 1. Use structured logs (JSON)
```ts
// ✅ Safe: structured log
function logUserAction(userId: string, action: string) {
  console.log({
    level: 'info',
    message: 'user.action',
    userId,
    action,
  });
}
```

JSON-encoded strings have newline characters escaped (`\n`).
The log file is one JSON object per line, regardless of input.

### 2. Sanitize user input (if using free-form logs)
```ts
function sanitize(input: string): string {
  return input
    .replace(/[\r\n]/g, '\\n')  // escape newlines
    .replace(/[\x00-\x1f\x7f]/g, '?');  // escape control chars
}

function logUserAction(userId: string, action: string) {
  console.log(`User ${userId} performed action ${sanitize(action)}`);
}
```

### 3. Limit log message length
```ts
function safeLog(message: string, maxLength: number = 1000): string {
  return message.length > maxLength ? message.slice(0, maxLength) + '...' : message;
}
```

A 1GB log message is a DoS vector. Cap it.

### 4. Don't log the raw user input
```ts
// ❌ Bad: log the raw input
function logComment(comment: Comment) {
  console.log(`User commented: ${comment.body}`);
}

// ✅ Good: log metadata, not content
function logComment(comment: Comment) {
  console.log({
    level: 'info',
    message: 'comment.created',
    userId: comment.userId,
    commentId: comment.id,
    length: comment.body.length,
    // Don't include comment.body
  });
}
```

## Specific fields to be careful with

- **User-provided names** (display name, email, URL)
- **User-provided content** (posts, comments, messages)
- **Headers** (User-Agent, Referer — can be controlled)
- **Query parameters** (visible in access logs)
- **Error messages** (from user input, like "Invalid email: X")

For each, sanitize before logging.

## Verification
- **Test:** `test/log-injection.test.ts > newline in user input
  doesn't create fake log lines` — passes
- **Live:** Log monitor alerts are based on real errors, not
  injected ones
- **Audit:** Quarterly review of log format + sanitization

## Gotchas
- **Sanitization can be defeated by Unicode.** Some Unicode
  characters look like newlines but aren't. Use a sanitizer
  that handles Unicode, or just use structured logging.
- **Log shipping to a third party** (Datadog, etc.) may have
  different sanitization needs. Use the third party's
  structured logging SDK.
- **Free-form logs are a code smell.** If your code logs
  free-form strings, refactor to structured logs.
- **The injection isn't just CR/LF.** A backspace character
  can also corrupt the terminal/log viewer. Escape ALL control
  characters.
- **Logs in a database** are also vulnerable. A newline in
  user input can break the log row's structure.

## Related
- `observability-three-pillars.md`
- `secure-headers.md`
- OWASP: https://owasp.org/www-community/attacks/Log_Injection
