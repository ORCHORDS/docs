# Circuit Breaker

The Circuit Breaker pattern is a critical resilience pattern that prevents cascading failures in distributed systems by temporarily halting requests to failing services.

## What It Does

A circuit breaker monitors service calls and automatically trips when failure thresholds are exceeded. It prevents the system from making futile attempts to contact failing services, allowing them time to recover while protecting the overall system from overload.

```java
public class CircuitBreaker {
    private enum State { CLOSED, OPEN, HALF_OPEN }
    private State state = State.CLOSED;
    private int failureCount = 0;
    private long lastFailureTime = 0;
    private final int failureThreshold = 5;
    private final long timeout = 30000; // 30 seconds
}
```

## Failure Protection

The circuit breaker protects against cascading failures by preventing requests to services that are currently failing. When a service consistently returns errors, the breaker trips and blocks all further calls until recovery.

```java
public boolean allowRequest() {
    if (state == State.OPEN) {
        if (System.currentTimeMillis() - lastFailureTime > timeout) {
            state = State.HALF_OPEN;
            return true; // Allow one test request
        }
        return false; // Reject all requests
    }
    return true; // Allow requests in CLOSED state
}
```

## Half-Open State

When the circuit breaker times out, it transitions to half-open state where a single test request is allowed through. If successful, the circuit closes again. If it fails, the circuit reopens for another timeout period.

```java
public void handleSuccess() {
    if (state == State.HALF_OPEN) {
        state = State.CLOSED;
        failureCount = 0;
    }
}

public void handleFailure() {
    if (state == State.HALF_OPEN) {
        state = State.OPEN;
        lastFailureTime = System.currentTimeMillis();
    }
}
```

## Timeout Configuration

Timeout determines how long the circuit remains open before attempting recovery. Too short and you'll keep failing; too long and you waste resources waiting for recovery.

```java
// Good timeout values depend on service characteristics
private final long timeout = 30000; // 30 seconds for most services
private final long timeout = 60000; // 1 minute for slower services
private final long timeout = 5000;  // 5 seconds for fast recovery services
```

## Retry Strategy

The circuit breaker doesn't eliminate retries but manages them intelligently. When in closed state, it allows normal retries. When open, it prevents retries entirely.

```java
public void executeWithRetry(Runnable operation) {
    int attempts = 0;
    while (attempts < maxRetries) {
        if (circuitBreaker.allowRequest()) {
            try {
                operation.run();
                circuitBreaker.recordSuccess();
                return;
            } catch (Exception e) {
                circuitBreaker.recordFailure();
                attempts++;
            }
        } else {
            // Circuit open - skip retries
            throw new CircuitBreakerOpenException();
        }
    }
}
```

## Resilience Benefits

The circuit breaker provides immediate protection against cascading failures, reduces system load during outages, and allows services to recover without being overwhelmed by requests.

## When to Trip

Trip when failure rate exceeds threshold or when specific failure patterns occur. Common triggers include:
- 5 consecutive failures within 1 minute
- 50% failure rate over 10 requests
- Specific timeout thresholds exceeded

```java
private boolean shouldTrip() {
    if (failureCount >= failureThreshold) {
        return true;
    }
    // Additional logic for time-based thresholds
    return false;
}
```

## Reset Strategies

Reset strategies determine when to attempt recovery:
1. **Time-based**:
