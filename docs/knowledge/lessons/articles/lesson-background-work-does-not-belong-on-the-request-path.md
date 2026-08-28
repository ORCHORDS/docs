# Lesson: Background Work Does Not Belong on the Request Path

Long-running or retryable tasks increase latency and couple user requests to unrelated downstream work. Move non-critical asynchronous work to queues or durable workflows when the response does not depend on completion.

Source: Cloudflare Workers Best Practices.