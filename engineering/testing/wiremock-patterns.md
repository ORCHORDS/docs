# wiremock-patterns

**Issue:** Mocking external HTTP services in Java/Kotlin integration tests with WireMock
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Java services that call external APIs (payment gateways, third-party APIs) need deterministic mock responses in tests.

## Pattern / Solution
```java
// JUnit 5 with WireMock
@WireMockTest(httpPort = 8089)
class PaymentServiceTest {

  @Test
  void processPayment_success(WireMockRuntimeInfo wmRuntimeInfo) {
    stubFor(post(urlEqualTo("/payments"))
      .withHeader("Content-Type", equalTo("application/json"))
      .willReturn(aResponse()
        .withStatus(200)
        .withHeader("Content-Type", "application/json")
        .withBody("""{ "id": "pay_123", "status": "succeeded" }""")));

    PaymentService service = new PaymentService("http://localhost:8089");
    Payment result = service.charge(new ChargeRequest(1000, "usd"));

    assertThat(result.getStatus()).isEqualTo("succeeded");
    verify(postRequestedFor(urlEqualTo("/payments")));
  }
}
```

Standalone WireMock server for all languages:
```bash
java -jar wiremock-standalone.jar --port 8089
curl -X POST http://localhost:8089/__admin/mappings -d '{"request": {"url": "/api"}, "response": {"status": 200}}'
```

## Gotchas
- WireMock 3.x requires JDK 11+ and JUnit 5.8+
- `verify()` checks call count and request details — use for command endpoints
- Use `WireMockExtension` for more control over lifecycle

## Related
- `mock-server-msw.md`
- `contract-testing-pact.md`
