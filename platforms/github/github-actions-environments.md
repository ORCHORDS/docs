# GitHub Actions Environments

GitHub Actions environments provide a powerful way to manage deployments across different stages of your software development lifecycle. They offer protection rules, required reviewers, and secure secret management that help ensure safe and controlled deployments.

## Symptom

When deploying applications to production, teams often encounter issues with unauthorized deployments, missing environment variables, or uncontrolled access to critical environments. Without proper environment configuration, accidental deployments to production can occur, leading to service disruptions and security vulnerabilities.

## Gotchas

Environment protection rules can be bypassed if not properly configured. Required reviewers must be carefully managed to avoid deployment bottlenecks. Environment secrets are only accessible within the specific environment context, not globally across all workflows.

## Environment Protection Rules

Protection rules act as gatekeepers for your environments, ensuring deployments meet specific criteria before proceeding:

```yaml
# .github/workflows/deploy.yml
name: Deploy Application
on:
  push:
    branches:
      - main
      - release/*
jobs:
  deploy:
    runs-on: ubuntu-latest
    environment:
      name: production
      # Protection rules configuration
      required_pull_request_reviews:
        number_of_reviewers: 2
        dismiss_stale_reviews: true
        require_code_owner_reviews: true
```

## Required Reviewers

Implementing required reviewers ensures that deployments are validated by team members before proceeding:

```yaml
# .github/workflows/deploy.yml
name: Production Deployment
on:
  push:
    branches:
      - main
jobs:
  deploy-production:
    runs-on: ubuntu-latest
    environment:
      name: production
      required_pull_request_reviews:
        number_of_reviewers: 1
        dismiss_stale_reviews: true
        reviewers:
          - username: "dev-lead"
          - username: "security-team"
```

## Deployment Branches

Configure which branches can deploy to specific environments:

```yaml
# .github/workflows/deploy.yml
name: Environment Deployment
on:
  push:
    branches:
      - main
      - develop
      - release/*
jobs:
  deploy-staging:
    runs-on: ubuntu-latest
    environment:
      name: staging
      # Only allow deployments from specific branches
    steps:
      - uses: actions/checkout@v4
      - run: echo "Deploying to staging"

  deploy-production:
    runs-on: ubuntu-latest
    environment:
      name: production
      # Production only accepts main branch
    steps:
      - uses: actions/checkout@v4
      - run: echo "Deploying to production"
```

## Environment Secrets

Securely manage sensitive data for each environment:

```yaml
# .github/workflows/deploy.yml
name: Secure Deployment
on:
  push:
    branches:
      - main
jobs:
  deploy:
    runs-on: ubuntu-latest
    environment:
      name: production
