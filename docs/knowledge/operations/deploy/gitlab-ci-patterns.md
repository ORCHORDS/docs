# gitlab-ci-patterns

**Issue:** Structuring GitLab CI/CD pipelines for multi-stage deployments with environments and approvals
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
GitLab CI has powerful native features (environments, protected variables, review apps, manual approvals) that are under-used. This entry covers patterns for production-grade GitLab pipelines.

## Pattern / Solution
`.gitlab-ci.yml` with stages, caching, and protected environments:
```yaml
stages: [build, test, deploy-staging, approve, deploy-production]

variables:
  IMAGE: $CI_REGISTRY_IMAGE:$CI_COMMIT_SHORT_SHA
  DOCKER_BUILDKIT: "1"

default:
  image: docker:24
  tags: [docker]
  interruptible: true

# Reusable YAML anchors
.deploy-template: &deploy-template
  image: bitnami/kubectl:latest
  before_script:
    - kubectl config use-context $KUBE_CONTEXT

build:
  stage: build
  services: [docker:24-dind]
  cache:
    key:
      files: [package-lock.json]
    paths: [node_modules/]
  script:
    - docker login -u $CI_REGISTRY_USER -p $CI_REGISTRY_PASSWORD $CI_REGISTRY
    - docker build --cache-from $CI_REGISTRY_IMAGE:latest -t $IMAGE .
    - docker push $IMAGE
    - docker tag $IMAGE $CI_REGISTRY_IMAGE:latest
    - docker push $CI_REGISTRY_IMAGE:latest

test:
  stage: test
  image: node:20-alpine
  script:
    - npm ci
    - npm test -- --coverage
  coverage: '/Statements\s*:\s*(\d+\.\d+)/'
  artifacts:
    reports:
      junit: junit.xml
      coverage_report:
        coverage_format: cobertura
        path: coverage/cobertura-coverage.xml

deploy-staging:
  <<: *deploy-template
  stage: deploy-staging
  environment:
    name: staging
    url: https://staging.myapp.example.com
  script:
    - helm upgrade --install myapp ./chart --set image.tag=$CI_COMMIT_SHORT_SHA -n staging
  only: [main]

approve-production:
  stage: approve
  when: manual
  allow_failure: false
  environment:
    name: production
  script: [echo "Approved"]
  only: [main]

deploy-production:
  <<: *deploy-template
  stage: deploy-production
  environment:
    name: production
    url: https://myapp.example.com
  script:
    - helm upgrade --install myapp ./chart --set image.tag=$CI_COMMIT_SHORT_SHA -n production
  needs: [approve-production]
  only: [main]
```

## Gotchas
- Protected environments restrict who can trigger manual jobs — configure approvers in Settings > CI/CD > Environments
- `interruptible: true` cancels older pipeline runs for the same branch when a new push arrives; safe for non-deployment jobs
- `CI_REGISTRY_PASSWORD` is a short-lived token; refresh with `docker login` at the start of each job that needs it
- YAML anchors (`<<: *template`) are resolved at parse time; they cannot reference variables defined elsewhere in the file
- `when: manual` + `allow_failure: false` blocks the pipeline until the job is triggered; without `allow_failure: false` the pipeline continues past the manual gate

## Related
- `circleci-config-patterns.md`
- `github-actions-self-hosted.md`
- `deployment-approval-workflow.md`
