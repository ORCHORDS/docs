# GitHub API Rate Limits and Strategies

## Overview

GitHub API rate limits are crucial for maintaining reliable automation and integration workflows. Understanding these limits helps prevent your applications from being temporarily blocked or throttled, ensuring consistent access to GitHub's services.

## Symptom

When you exceed GitHub's rate limits, you'll encounter HTTP 403 Forbidden responses with a `X-RateLimit-Remaining` header of 0. The response body typically includes:
```json
{
  "message": "API rate limit exceeded for [IP]",
  "documentation_url": "https://docs.github.com/rest/overview/resources-in-the-rest-api#rate-limiting"
}
```

## Gotchas

- **Rate limits reset only at the hour boundary**, not immediately after exceeding limits
- **Different endpoints have different rate limits** - some are per-second, others per-hour
- **OAuth tokens and personal access tokens share the same quota**
- **Secondary rate limits** can be triggered by excessive requests to a single endpoint
- **GraphQL queries count against your GraphQL limit**, not REST limits

## REST vs GraphQL Limits

GitHub implements different rate limits for REST and GraphQL APIs:

### REST API Limits
- **Unauthenticated**: 60 requests per hour
- **Authenticated**: 5,000 requests per hour
- **Per endpoint**: Some endpoints have stricter limits (e.g., search: 30/hour)

### GraphQL API Limits
- **Unauthenticated**: 5,000 requests per hour
- **Authenticated**: 5,000 requests per hour
- **Per query**: Each query counts toward your limit based on complexity

## Conditional Requests and ETag

Use conditional requests to avoid unnecessary API calls:

```javascript
// Using ETags for caching
const response = await fetch('https://api.github.com/repos/octocat/Hello-World', {
  headers: {
    'If-None-Match': localStorage.getItem('etag'),
    'Authorization': `token ${process.env.GITHUB_TOKEN}`
  }
});

if (response.status === 304) {
  console.log('No changes since last request');
} else {
  const data = await response.json();
  localStorage.setItem('etag', response.headers.get('ETag'));
}
```

## Secondary Rate Limits

Secondary rate limits are triggered by excessive requests to a single endpoint:

```javascript
// Handle secondary rate limits with retry logic
async function fetchWithRetry(url, options, maxRetries = 3) {
  for (let i = 0; i < maxRetries; i++) {
    try {
      const response = await fetch(url, options);

      if (response.status === 429) {
        const retryAfter = parseInt(response.headers.get('Retry-After')) || 60;
        console.log(`Rate limited. Waiting ${retryAfter} seconds...`);
        await new Promise(resolve => setTimeout(resolve,
