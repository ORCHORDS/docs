# api-testing-rest-assured

**Issue:** Testing REST APIs in Java/Kotlin projects with REST Assured
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Java backend services need API-level integration tests. REST Assured provides a fluent DSL for HTTP assertions.

## Pattern / Solution
```xml
<!-- pom.xml -->
<dependency>
  <groupId>io.rest-assured</groupId>
  <artifactId>rest-assured</artifactId>
  <version>5.4.0</version>
  <scope>test</scope>
</dependency>
```

```java
import static io.restassured.RestAssured.*;
import static org.hamcrest.Matchers.*;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class UserApiTest {

  @LocalServerPort int port;

  @BeforeEach
  void setUp() { RestAssured.port = port; }

  @Test
  void createUser_returns201() {
    given()
      .contentType("application/json")
      .body("""{ "name": "Alice", "email": "alice@example.com" }""")
    .when()
      .post("/api/users")
    .then()
      .statusCode(201)
      .body("name", equalTo("Alice"))
      .body("id", notNullValue());
  }
}
```

## Gotchas
- Use `@Transactional` + `@Rollback` on tests to clean up data
- `RANDOM_PORT` prevents port conflicts in parallel test runs
- Use `RequestSpecification` for shared auth headers

## Related
- `api-testing-supertest.md`
- `integration-test-api.md`
