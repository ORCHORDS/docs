# Lesson: Floating Promises Become Silent Loss

Unawaited asynchronous work can disappear when a runtime finishes the request lifecycle. Every promise should be awaited, returned, or explicitly attached to a supported background-work mechanism.

Source: Cloudflare Workers Best Practices.