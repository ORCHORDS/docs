# docker-multi-stage-build

**Issue:** Using Docker multi-stage builds to produce small, secure production images without bloating them with build tooling
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Single-stage Dockerfiles include compilers, dev dependencies, and build caches in the production image, increasing attack surface and image size. Multi-stage builds copy only the compiled output into a minimal runtime image.

## Pattern / Solution
**Node.js API — multi-stage example**
```dockerfile
# Stage 1: install dependencies and build
FROM node:22-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci --include=dev
COPY . .
RUN npm run build

# Stage 2: production runtime (only prod deps + built output)
FROM node:22-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production

# Create non-root user
RUN addgroup -S app && adduser -S app -G app

COPY package*.json ./
RUN npm ci --omit=dev && npm cache clean --force

COPY --from=builder /app/dist ./dist

USER app
EXPOSE 3000
CMD ["node", "dist/server.js"]
```

**Go binary — smallest possible image**
```dockerfile
FROM golang:1.23-alpine AS builder
WORKDIR /app
COPY go.* ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o server ./cmd/server

FROM scratch AS runtime
COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/
COPY --from=builder /app/server /server
ENTRYPOINT ["/server"]
```

**Python — with venv isolation**
```dockerfile
FROM python:3.13-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

FROM python:3.13-slim AS runtime
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY . .
CMD ["gunicorn", "app:create_app()", "-b", "0.0.0.0:8000"]
```

## Gotchas
- `COPY --from=builder` paths are relative to the stage's WORKDIR, not the host
- The `scratch` base image has no shell, no CA certs, and no user management — copy what you need explicitly
- `npm ci --omit=dev` (not `--production`) is the current flag name in npm 9+
- Layer order matters for cache: copy dependency manifests before source code, always

## Related
- `docker-layer-caching-ci.md`
- `container-image-tagging.md`
- `artifact-versioning-strategy.md`
