# circleci-config-patterns

**Issue:** Structuring CircleCI config for speed, reuse, and reliable deployments
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Slow CircleCI pipelines block developers. Mis-configured orbs and missing cache keys cause flaky builds. This entry covers performance and reliability patterns for `.circleci/config.yml`.

## Pattern / Solution
Optimised config with orbs, caching, and parallelism:
```yaml
version: 2.1

orbs:
  node: circleci/node@5
  docker: circleci/docker@2
  slack: circleci/slack@4

executors:
  node-executor:
    docker:
      - image: cimg/node:20.0
    resource_class: medium

commands:
  restore-npm-cache:
    steps:
      - restore_cache:
          keys:
            - npm-v1-{{ checksum "package-lock.json" }}
            - npm-v1-
      - run: npm ci
      - save_cache:
          key: npm-v1-{{ checksum "package-lock.json" }}
          paths: [node_modules]

jobs:
  test:
    executor: node-executor
    parallelism: 4
    steps:
      - checkout
      - restore-npm-cache
      - run:
          name: Run tests (split by timing)
          command: |
            TESTFILES=$(circleci tests glob "**/*.test.ts" | circleci tests split --split-by=timings)
            npx jest $TESTFILES --ci --reporters=default --reporters=jest-junit
          environment:
            JEST_JUNIT_OUTPUT_DIR: test-results
      - store_test_results:
          path: test-results
      - store_artifacts:
          path: coverage

  build-push:
    executor: node-executor
    steps:
      - checkout
      - setup_remote_docker:
          docker_layer_caching: true
      - docker/build:
          image: myorg/myapp
          tag: $CIRCLE_SHA1
      - docker/push:
          image: myorg/myapp
          tag: $CIRCLE_SHA1

workflows:
  ci-cd:
    jobs:
      - test
      - build-push:
          requires: [test]
          filters:
            branches:
              only: main
      - slack/on-hold:
          requires: [build-push]
          filters:
            branches:
              only: main
      - approve-deploy:
          type: approval
          requires: [slack/on-hold]
      - deploy:
          requires: [approve-deploy]
```

## Gotchas
- `parallelism: N` requires `circleci tests split` to distribute work; without it, all N containers run the same tests
- `docker_layer_caching: true` costs extra credits but saves significant time on large images
- Cache keys with `{{ checksum }}` invalidate when the lock file changes; always have a fallback key (`npm-v1-`)
- `setup_remote_docker` creates a separate VM; files written there are not in the main executor and vice versa
- Orb versions should be pinned (`@5.1.0`) in production, not floating (`@5`)

## Related
- `github-actions-self-hosted.md`
- `gitlab-ci-patterns.md`
- `docker-layer-caching-ci.md`
