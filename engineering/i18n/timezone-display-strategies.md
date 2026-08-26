# Timezone Display Strategies

## User Preference vs Browser Detection

When displaying times to users, you must decide between honoring their explicit preferences or automatically detecting their browser timezone. User preferences offer better control and consistency across devices, while automatic detection provides convenience but may be inaccurate.

```javascript
// User preference approach
const userTimezone = localStorage.getItem('user-timezone') || Intl.DateTimeFormat().resolvedOptions().timeZone;
const displayTime = new Date(timestamp).toLocaleString('en-US', {
  timeZone: userTimezone,
  hour: '2-digit',
  minute: '2-digit'
});

// Browser detection approach
const browserTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
const timeWithDetection = new Date(timestamp).toLocaleString('en-US', {
  timeZone: browserTimezone,
  hour: '2-digit',
  minute: '2-digit'
});
```

## Storing UTC Timestamps

Always store timestamps in UTC format to avoid timezone confusion. Convert to local time only for display purposes. This ensures consistency across all systems and prevents daylight saving time issues.

```javascript
// Store in UTC
const utcTimestamp = new Date().toUTCString();
// Or use Unix timestamp (seconds since epoch)
const unixTimestamp = Math.floor(Date.now() / 1000);

// Convert to local display time
const localTime = new Date(unixTimestamp * 1000).toLocaleString('en-US', {
  timeZone: userTimezone
});
```

## DST Edge Cases

Daylight saving time transitions create ambiguous times that require careful handling. When a clock "falls back," the same local time occurs twice, while "springing forward" skips an hour entirely.

```javascript
// Handle DST transitions properly
function getLocalTimeWithDST(timestamp, timezone) {
  const date = new Date(timestamp);
  // Use toLocaleString with timezone for automatic DST handling
  return date.toLocaleString('en-US', {
    timeZone: timezone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  });
}

// For ambiguous times, use explicit timezone offset
const options = {
  timeZone: 'America/New_York',
  hour12: false,
  year: 'numeric',
  month: '2-digit',
  day: '2
