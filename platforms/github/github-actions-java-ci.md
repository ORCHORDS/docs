# github-actions-java-ci

**Issue:** Java/Maven/Gradle CI with dependency caching and test reporting
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Java projects using Maven or Gradle need CI that caches `.m2` or Gradle caches and publishes Surefire/JUnit XML reports.

## Pattern / Solution
Maven:
```yaml
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          java-version: '21'
          distribution: temurin
          cache: maven
      - run: mvn -B verify --no-transfer-progress
```
Gradle:
```yaml
      - uses: actions/setup-java@v4
        with:
          java-version: '21'
          distribution: temurin
          cache: gradle
      - run: ./gradlew test
      - uses: actions/upload-artifact@v4
        if: failure()
        with:
          name: test-reports
          path: build/reports/tests/
```

## Gotchas
- `distribution: temurin` (Eclipse Adoptium) is the most common open-source JDK choice.
- The `cache: maven` shorthand in `setup-java` hashes `**/pom.xml` automatically.
- Gradle daemon can cause port conflicts on self-hosted runners; add `--no-daemon` for CI.
- `-B` (batch mode) suppresses Maven download progress noise.

## Related
- `github-actions-cache-dependencies.md`
- `github-actions-upload-release-assets.md`
