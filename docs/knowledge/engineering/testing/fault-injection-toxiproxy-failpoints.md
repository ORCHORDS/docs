# Fault Injection Toxiproxy Failpoints

Distributed systems fail in distributed ways: a database returns 5xx, a downstream service
times out, a TCP connection is severed mid-request, a network path adds 800ms of latency. The
SUT under integration test must be exercised against these failures, not only against the
happy path. Toxiproxy, the Shopify-maintained proxy for resilience testing, sits between the
SUT and its dependencies and applies the failure: it can drop connections, return errors,
introduce latency, throttle bandwidth, or corrupt responses, all driven by a CLI or HTTP API.
*Failpoints* is the complementary concept: a controlled code path inside the SUT itself
where a fault is injected from configuration, allowing failures that no network proxy can
inject (for example, a panic in a goroutine, or a partial cache eviction). The two together
cover the failure surface of a distributed system end-to-end.

## Scope

Covers the design and operation of fault injection via Toxiproxy for integration and
end-to-end tests, plus the use of failpoints for in-process fault simulation. Applies to
testing distributed systems whose dependencies run as separate processes (database,
cache, message broker, third-party API). Does not cover production chaos engineering, where
the failures are applied to live traffic; the scope here is the test environment.

## Workflow or implementation guidance

1. **Map dependencies to proxies.** Each dependency the SUT talks to is a candidate for
   Toxiproxy. For each candidate, decide whether the test environment runs the dependency
   directly or behind a Toxiproxy proxy. The proxy is invisible to the SUT; the SUT's
   connection string points at the proxy's listening port, and the proxy forwards to the
   real dependency. Map the SUT's configuration to the proxy topology in test only; the
   production configuration is unchanged.
2. **Design the fault set deliberately.** A "drop all traffic" fault is easy to write and
   tells you almost nothing about the system. The fault set should mirror the failure modes
   the SUT claims to handle in its design:
   - connection refused at startup (the dependency is unavailable);
   - connection severed mid-request (network blip after the request started);
   - slow dependency (latency added to every request);
   - intermittent errors (one in five requests returns 5xx);
   - dependency returns malformed data;
   - dependency disconnects and reconnects.
   Each fault tests a specific resilience claim; the test that exercises it asserts the
   claim is honoured.
3. **Use Toxiproxy's API to apply the fault.** The CLI exposes `toxic add` for each proxy,
   with named toxics (`latency`, `timeout`, `slow_close`, `bandwidth`, `reset_peer`,
   `slicer`) and configurable parameters. The test code applies the toxic before the SUT
   call, exercises the SUT, then removes the toxic before teardown so subsequent tests are
   unaffected. Each test owns its toxics; no test inherits state from another.
4. **Combine Toxiproxy with failpoints for in-process faults.** Toxiproxy cannot simulate a
   goroutine panic, a disk-full error, a partial cache eviction, or a clock jump. For those,
   the SUT exposes a failpoint mechanism: a conditional fault controlled by configuration,
   environment variable, or runtime signal. A failpoint is exercised by setting the
   trigger, calling the SUT, then unsetting the trigger. Failpoints are a maintenance
   burden; expose only the ones the SUT's design actually depends on, and audit them
   regularly.
5. **Run fault-injected tests in their own stage.** Fault-injected tests are inherently
   slower (the proxy introduces latency by design) and noisier (a flaky network on a
   happy-path test is a bug). Run them in a dedicated CI stage with a separate threshold for
   pass rate and a separate retry policy. Mixing happy-path and fault-injected tests in the
   same stage produces flake reports that conflate the two.
6. **Assert on the SUT's response, not on the fault.** A test that asserts "the toxic was
   applied" tells you nothing about whether the SUT handled it. The assertion should be on
   the SUT's behaviour under the fault: did the retry succeed, did the circuit open, did
   the user receive a graceful error, did the system log the failure with the expected
   structured fields.
7. **Keep the proxy's lifetime bounded.** A Toxiproxy instance started by a test must be
   stopped by that test, even on failure. A teardown step in the test framework is the
   safe place; an unstopped proxy consumes ports and leaks state into the next test.
8. **Treat the fault set as a living artefact.** A new resilience claim in the SUT's design
   is a new fault in the test set. A removed claim is a removed fault. The fault catalogue
   lives in the repo, versioned with the SUT.

A representative Toxiproxy workflow in a Node-based integration test:

```ts
import { Toxiproxy } from 'toxiproxy-node-client';

const proxy = await toxiproxy.get('redis-primary');
await proxy.addToxic('latency', { latency: 800, jitter: 200 });
try {
  await expect(client.get('key')).rejects.toThrow(/timeout/);
} finally {
  await proxy.removeToxic('latency');
}
```

The toxic is applied for the duration of the single call; the `finally` ensures it is
removed even if the assertion fails.

## Controls

- Toxiproxy proxies are created and torn down per test, not per suite; no shared proxy
  carries state between tests.
- The fault catalogue is committed to the repository and reviewed when the SUT's
  resilience claims change.
- Failpoints are listed and audited; any failpoint that has not been exercised in the
  last release is a candidate for removal.
- Fault-injected tests run in a dedicated CI stage with a separate flake threshold.
- The proxy's listen port is bounded to the test network; production configurations never
  reference the proxy.

## Validation evidence

- A claim in the SUT's design ("retry three times on transient 5xx") is exercised by a
  fault-injected test, and the test asserts the retry succeeded. Removing the retry from
  the SUT causes the test to fail.
- A claim that is no longer in the SUT's design has its fault removed from the catalogue;
  the catalogue diff is reviewed each release.
- A Toxiproxy toxic that is not removed by a failing test is detected by a teardown
  assertion (the next test reports "no toxics" on the proxy). Persistent leaks are caught
  by the test framework, not by a long debugging session.
- The failpoint list and the resilience-claim list correspond one-to-one; a failpoint
  without a corresponding claim is removed.

## Failure modes and correction

- *Toxiproxy tests slow CI to a crawl.* Limit the fault catalogue to the resilience claims
  the SUT actually makes; run only the relevant subset per change.
- *Toxics bleed between tests.* A test that forgets to remove its toxic leaves the proxy in
  a state that breaks the next test. Wrap every toxic application in a `try/finally` or
  equivalent teardown.
- *Failpoints accumulate.* A failpoint added for a one-off investigation is never removed.
  Audit the failpoint list at every release; remove unused ones.
- *Tests assert on the fault rather than on the response.* Reframe the assertion around the
  SUT's contract under the fault; the fault is the precondition, not the test.
- *Fault-injected tests flake.* Increase the SUT's tolerance window before asserting; do
  not lower the fault's intensity to make the test pass.
- *Proxy ports collide.* Pin proxy ports to a per-test allocation; let the proxy API
  choose a free port.
- *Fault set drifts from the SUT's design.* The catalogue is unowned. Assign ownership;
  review the catalogue with the design.

## Limitations

- Toxiproxy operates at the network layer; it cannot inject faults that originate inside
  the SUT's process (memory pressure, CPU starvation, clock skew) — those require
  failpoints or kernel-level tools.
- A simulated fault is not a real fault. A 5xx returned by Toxiproxy is byte-identical to
  a 5xx returned by a real dependency, but the SUT's reaction may differ in the presence
  of additional signals (TCP RST vs slow close, full timeout vs partial response).
- Toxiproxy adds a network hop; tests run slower than they would against the dependency
  directly. Performance budgets for tests must accommodate this.
- Failpoints require the SUT to be instrumented, which is a maintenance cost. Adding a
  failpoint for every possible fault is engineering overhead; the catalogue must stay
  small.
- Toxiproxy tests cannot exercise failures that occur before the connection is established
  (DNS failure, TLS handshake failure) without additional tooling.

## Canonical sources

- Shopify, *Toxiproxy* (repository with toxic types, API, and usage examples):
  https://github.com/Shopify/toxiproxy
- Testcontainers, *Testcontainers documentation* (orchestrating dependent services behind
  Toxiproxy in containerised test environments): https://testcontainers.org/
- Principles of Chaos Engineering, *Principles of Chaos* (steady-state hypothesis and
  blast-radius discipline for fault injection in test):
  https://principlesofchaos.org/
