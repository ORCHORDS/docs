# graceful-shutdown-patterns

**Issue:** Implementing graceful shutdown in services to avoid dropped requests during deployments
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Without graceful shutdown, rolling deployments cause 502 errors as pods are terminated mid-request. Proper shutdown handling ensures in-flight requests complete before the process exits.

## Pattern / Solution
HTTP server graceful shutdown (Go):
```go
srv := &http.Server{Addr: ":8080", Handler: router}

go func() {
    if err := srv.ListenAndServe(); err != http.ErrServerClosed {
        log.Fatalf("Server error: %v", err)
    }
}()

quit := make(chan os.Signal, 1)
signal.Notify(quit, syscall.SIGTERM, syscall.SIGINT)
<-quit

log.Println("Shutting down server...")
ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
defer cancel()

if err := srv.Shutdown(ctx); err != nil {
    log.Fatalf("Forced shutdown: %v", err)
}
log.Println("Server exited")
```

Python (FastAPI + uvicorn):
```python
import signal
import asyncio
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    yield
    # Shutdown — cleanup runs here
    await database.disconnect()
    await redis_client.close()

app = FastAPI(lifespan=lifespan)
```

Node.js with express:
```javascript
const server = app.listen(8080);
let shuttingDown = false;

process.on('SIGTERM', () => {
  shuttingDown = true;
  server.close(() => process.exit(0));
  setTimeout(() => process.exit(1), 30_000).unref();
});

// Reject new requests during shutdown
app.use((req, res, next) => {
  if (shuttingDown) {
    res.setHeader('Connection', 'close');
    return res.status(503).json({ error: 'Service shutting down' });
  }
  next();
});
```

Kubernetes shutdown sequence:
```
1. kubectl delete pod / rolling update triggered
2. Pod removed from Service endpoints (async)
3. preStop hook runs (use sleep 5 to wait for LB deregistration)
4. SIGTERM sent to PID 1
5. App drains in-flight requests
6. Process exits (or SIGKILL after terminationGracePeriodSeconds)
```

## Gotchas
- PID 1 in a container does not forward signals to child processes; use `exec` form CMD or `tini` as init process
- `CMD ["npm", "start"]` spawns a shell that does not forward SIGTERM; use `CMD ["node", "server.js"]` instead
- Load balancer deregistration happens asynchronously — the `preStop: sleep` hack is necessary in most Kubernetes setups
- `SIGKILL` cannot be caught; always ensure your drain completes within `terminationGracePeriodSeconds`
- WebSocket connections require explicit close frames on shutdown; check your WS library's shutdown API

## Related
- `database-connection-drain.md`
- `kubernetes-rolling-update.md`
- `health-check-readiness-patterns.md`
- `zero-downtime-deploys.md`
