# Docker Multi-Stage Builds

Multi-stage builds are a powerful Docker feature that allows you to use multiple FROM statements in a single Dockerfile, enabling you to create optimized production images by separating build dependencies from runtime requirements.

## Builder vs Runtime Images

The fundamental concept involves using one stage for building your application and another for running it. The builder stage contains all development tools, compilers, and dependencies needed during compilation, while the runtime stage only includes the minimal components required to execute your application.

```dockerfile
# Builder stage
FROM node:16 AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production
COPY . .
RUN npm run build

# Runtime stage
FROM node:16-alpine AS runtime
WORKDIR /app
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/node_modules ./node_modules
EXPOSE 3000
CMD ["node", "dist/index.js"]
```

## Layer Caching Optimization

Multi-stage builds significantly improve layer caching by allowing you to isolate build dependencies. Changes in your source code only affect the builder stage, while runtime image layers remain unchanged.

```dockerfile
FROM python:3.9 AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt  # Cached if requirements.txt doesn't change

FROM python:3.9-slim AS runtime
WORKDIR /app
COPY --from=builder /usr/local/lib/python3.9/site-packages /usr/local/lib/python3.9/site-packages
COPY --from=builder /app/app.py .
CMD ["python", "app.py"]
```

## .dockerignore Configuration

Always use `.dockerignore` to exclude unnecessary files from the build context, reducing image size and build times.

```dockerfile
# .dockerignore
node_modules
npm-debug.log
.git
.gitignore
README.md
.env
.nyc_output
coverage
.nyc_output
```

## Distroless Images

Distroless images contain only your application and its runtime dependencies, eliminating unnecessary packages and reducing attack surface.

```dockerfile
FROM golang:1.19-alpine AS builder
WORKDIR /app
COPY . .
RUN go build -o main .

FROM gcr.io/distroless/base-debian11
COPY --from=builder /app/main /main
ENTRYPOINT ["/main"]
```
