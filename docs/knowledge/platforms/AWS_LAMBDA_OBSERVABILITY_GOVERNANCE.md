# AWS Lambda Observability Governance

## Purpose

AWS Lambda executes functions in response to triggers. Functions are stateless, short-lived, and managed by the platform. Effective observability captures invocation behavior, errors, duration, throttles, cold starts, and downstream dependencies. Governance ensures that every production function emits structured logs, distributed traces, and metrics; that alarms are configured for failure modes; and that traces correlate with the workload's transaction identity.

## Current context and source status

AWS Lambda supports AWS X-Ray active tracing, CloudWatch Logs Insights, CloudWatch metrics, and Lambda Insights (an extension providing enhanced metrics). Lambda response streaming and function URLs are available. Lambda's lifecycle, supported runtimes, and tracing mechanisms evolve; verify the current runtime support matrix before standardizing.

## Governance workflow and controls

### 1. Adopt structured logging

Every function MUST emit JSON logs with at least:

- correlation identifier propagated from the caller;
- AWS request ID;
- function name and version;
- cold-start indicator;
- severity level;
- latency for downstream calls.

Plain-text logs MUST NOT be used for production functions.

### 2. Enable distributed tracing

Activate AWS X-Ray active tracing on every production function. Instrument outbound HTTP and database calls so that traces cross function and service boundaries. Set sampling rules that preserve traces for errors and reduce sampling for successful low-value calls.

### 3. Emit custom metrics

Emit custom CloudWatch metrics for business-level events: orders processed, payments authorized, reties triggered. Metric names MUST follow a documented convention: namespace, dimension, unit.

### 4. Define alarms

Configure alarms for at least:

- error rate above baseline;
- p99 duration above the SLO;
- throttle count;
- iterator age for stream-based invocations;
- concurrent execution approaching the account limit.

### 5. Manage concurrency

Reserve concurrency for critical functions to prevent noisy-neighbor throttling. Configure provisioned concurrency for latency-sensitive paths. Track concurrent execution against the account quota.

### 6. Govern runtimes

Track AWS runtime deprecation announcements. Migrate off deprecated runtimes within the announced window. Treat a function running on a deprecated runtime as a security finding.

### 7. Code-signing

For sensitive workloads, configure Lambda code-signing. Reject functions whose code signature does not match the approved signing profile.

## Validation and evidence

- Structured-logging conformance check (sample recent invocations).
- X-Ray service map artifact.
- Alarm configuration and test history.
- Runtime support matrix with deprecation dates.
- Code-signing configuration and signature source.

## Failure correction

Common defects include unconfigured alarms, plain-text logs, and missing traces. Corrective actions include a conformance check that fails the deployment pipeline if a function lacks structured logging or tracing, and a runtime deprecation calendar with assigned owners.

## Limitations

- AWS Lambda is specific to AWS.
- Some tracing libraries add cold-start latency; measure the impact.
- CloudWatch Logs Insights has query limits.
- Function URLs lack the same observability surface as API Gateway.

## Canonical sources

- AWS Lambda Operator Guide, current edition.
- AWS X-Ray Developer Guide, current edition.
- AWS Lambda Insights documentation, current edition.

## Scope note

This article belongs to the platforms leaf and cross-references the engineering leaf for distributed tracing patterns, the operations leaf for incident response, and the security leaf for log handling.
