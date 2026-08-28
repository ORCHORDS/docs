# Lesson: Request State Should Not Live Globally

Reusable runtimes may serve many requests within the same process or isolate. Request-specific mutable global state can leak data across requests or create stale behavior.

Pass request state explicitly or store it in scoped runtime primitives.

Source: Cloudflare Workers Best Practices.