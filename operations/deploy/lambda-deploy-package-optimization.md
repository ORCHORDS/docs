# Lambda Deploy Package Optimization

## Overview

Optimizing AWS Lambda deployment packages is crucial for reducing cold start times, improving deployment speed, and minimizing costs. This guide covers essential techniques to optimize your Lambda functions, including layer separation, dependency management, bundling strategies, and performance tuning.

## Symptom

Slow cold starts, large deployment packages, high memory usage, and frequent timeouts are common symptoms of unoptimized Lambda functions. Functions with large package sizes (>50MB) often experience significant delays during initialization, especially when using provisioned concurrency.

## Gotchas

- **Layer dependencies**: Layers may conflict with local dependencies
- **Native modules**: Node.js native modules require specific architecture matching
- **Build artifacts**: Unnecessary files can bloat package size
- **Memory allocation**: Provisioned concurrency doesn't eliminate cold starts entirely
- **ESBuild compatibility**: Some packages may not work with tree-shaking

## Layer Separation

Separate your Lambda function dependencies into layers to share common libraries across multiple functions. This reduces individual package sizes and deployment times.

```json
// layer-config.json
{
  "layers": {
    "shared-deps": {
      "path": "./layers/shared",
      "dependencies": ["lodash", "axios"]
    },
    "database-deps": {
      "path": "./layers/database",
      "dependencies": ["pg", "sequelize"]
    }
  }
}
```

```yaml
# serverless.yml
provider:
  name: aws
  runtime: nodejs18.x

functions:
  apiHandler:
    handler: src/handlers/api.handler
    layers:
      - { Ref: SharedDepsLayer }
      - { Ref: DatabaseDepsLayer }

layers:
  SharedDepsLayer:
    path: layers/shared
    name: ${self:service}-${self:provider.stage}-shared-deps
```

## Prune DevDependencies

Remove development dependencies from production packages to significantly reduce size. Use npm prune with production flag.

```bash
# Remove dev dependencies before packaging
npm ci --production
# Or use package-lock.json with production flag
npm install --production --no-optional
```

```json
// package.json
{
  "scripts": {
    "build": "npm ci --production && npm run compile",
    "package": "npm run build && zip -r function.zip . -x 'node_modules/*' 'test/*' '.git/*'"
  },
  "dependencies": {
    "express": "^4.18.0",
    "lodash": "^4.17.21"
  },
  "devDependencies": {
    "jest": "^29.0.0",
    "eslint": "^8.0.0"
  }
}
```

## Native Modules

Handle native modules carefully by using pre-built binaries or avoiding them entirely. Use `--platform=linux` flag when building for Lambda.
