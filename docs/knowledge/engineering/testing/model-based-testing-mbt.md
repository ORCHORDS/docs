# Model-Based Testing (MBT)

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your test suite covers happy paths and a handful of edge cases, but you keep
finding bugs in unexpected state transitions — a user who cancels during
payment, a session that expires mid-wizard, an order that is edited after
shipping. Manual test case design misses these paths because humans think
linearly; the system's state space is combinatorial.

## Context

Model-Based Testing (MBT) uses a formal model of the system under test —
typically a finite state machine (FSM) or extended finite state machine
(EFSM) — to automatically generate test cases. You describe the states your
system can be in, the transitions between them, and the guards/actions on
each transition. The MBT tool then walks the graph and generates test paths
that achieve a specified coverage criterion (all states, all transitions, all
transition pairs, or random walks of a given length).

## How MBT works

1. **Model the system** — draw a directed graph where nodes are states
   (e.g., `LoggedOut`, `LoggedIn`, `CartFilled`, `CheckingOut`, `Paid`) and
   edges are actions (e.g., `login`, `addItem`, `checkout`, `pay`).
2. **Add guards and data** — EFSM models add conditions (`cartSize > 0`)
   and data operations (`cartSize++`) to transitions.
3. **Choose coverage criterion** — "visit all edges" (transition coverage),
   "visit all edge pairs" (2-switch coverage), or "random walk for N steps."
4. **Generate test paths** — the MBT tool traverses the graph and outputs
   ordered sequences of actions.
5. **Bind to test code** — each action in the model maps to a test function
   that drives the real system (Selenium click, API call, etc.).
6. **Execute and verify** — run the generated paths against the SUT. Each
   state has assertions (oracles) that verify the system matches the model.

## Tools

| Tool | Language | Model format | Coverage algorithms | License |
|---|---|---|---|---|
| GraphWalker | Java | JSON/GRAPHML (yEd) | Random, A*, all edges, all vertices | MIT |
| Modbat | Scala/JVM | Scala DSL | All transitions, weighted random | BSD |
| Conformiq | Any (commercial) | UML state machines | Exhaustive symbolic | Commercial |
| NModel | .NET | C# model classes | All states, all transitions | MS-PL |
| spec-explorer | .NET | Spec Explorer models | Exhaustive | Microsoft |

**GraphWalker** is the most widely adopted open-source MBT tool. Models are
drawn in yEd as directed graphs and exported as GRAPHML or JSON.

## GraphWalker example

```java
// Model interface — generated from the graph
public interface ShoppingCartModel {
    void e_Login();       // edge: login action
    void e_AddItem();     // edge: add item to cart
    void e_Checkout();    // edge: start checkout
    void e_Pay();         // edge: complete payment
    void v_LoggedOut();   // vertex: verify logged-out state
    void v_LoggedIn();    // vertex: verify logged-in state
    void v_CartFilled();  // vertex: verify cart has items
    void v_Paid();        // vertex: verify payment complete
}

// Test implementation
public class ShoppingCartTest implements ShoppingCartModel {
    @Override
    public void e_Login() {
        driver.findElement(By.id("login")).click();
        driver.findElement(By.id("email")).sendKeys("test@example.com");
        driver.findElement(By.id("submit")).click();
    }

    @Override
    public void v_LoggedIn() {
        assertTrue(driver.findElement(By.id("user-menu")).isDisplayed());
    }
    // ... other methods
}
```

```bash
# Run GraphWalker with "cover all edges" criterion
java -jar graphwalker-cli.jar offline \
  --model shopping-cart.graphml \
  "random(edge_coverage(100))"
```

## When to use MBT

- **Stateful workflows** — checkout, onboarding, approval chains, document
  lifecycle. Any flow with multiple states and transitions.
- **Protocol testing** — network protocols, API state machines, OAuth flows.
- **Regression test generation** — regenerate tests when the model changes
  instead of manually updating test cases.
- **Exploratory coverage** — find unexpected state transition bugs that
  linear happy-path tests miss.

## When NOT to use MBT

- **Stateless APIs** — CRUD endpoints without complex state transitions are
  better served by property-based testing or contract testing.
- **Pure UI visual testing** — MBT tests behavior, not appearance. Combine
  with visual regression testing for UI.
- **When the model would be as complex as the code** — if modeling the system
  is harder than testing it directly, MBT adds cost without value.

## Anti-patterns

- **Modeling everything** — start with the highest-value stateful workflow
  (e.g., the checkout flow), not the entire application.
- **Model without oracles** — generating paths without assertions at each
  state is just random clicking. Every vertex must assert system state.
- **Stale models** — if the model is not updated when the system changes, the
  generated tests will fail for the wrong reasons. Treat the model as a
  living artifact in version control.
- **Ignoring data variations** — FSM models without data (EFSM) miss
  data-dependent bugs. Add guards and data to transitions.

## Gotchas

- **State explosion** — complex systems with many variables create
  exponentially large state spaces. Use abstraction (group similar states)
  and data reduction techniques.
- **Model accuracy** — a model that doesn't match the real system produces
  useless tests. Validate the model against the existing test suite first.
- **GraphWalker requires Java** — the CLI runs on JVM. For non-Java
  projects, use the REST API mode or the Python wrapper
  (`MBT_GraphWalker_Python`).
- **Coverage criterion choice matters** — "all edges" is the minimum useful
  criterion. "All edge pairs" catches more bugs but generates exponentially
  more paths. Start with "all edges" and escalate if bugs slip through.

## Verification

- Compare MBT-generated test coverage against your existing manual test
  suite. MBT should cover paths your manual suite misses.
- Track bugs found by MBT-generated tests vs. manually written tests.
- Model coverage report: verify 100% edge coverage (minimum) or 100%
  edge-pair coverage (thorough).

## Related

- `documentation/docs/policies/testing/property-based-testing-fast-check.md`
- `documentation/docs/policies/testing/test-pyramid-strategy.md`
- `documentation/docs/policies/testing/auth-flow-testing-strategy.md`
- `documentation/docs/policies/patterns/circuit-breaker-pattern.md`

## Source URLs (verified 2026-08-16)

- Model-based testing using state machines — https://abstracta.us/blog/software-testing/model-based-testing-using-state-machines/
- MBT using GraphWalker — https://medium.com/@nehabimal2003/model-based-testing-mbt-using-graphwalker-76284eba6817
- Practical model-based testing — https://medium.com/cyberark-engineering/practical-model-based-testing-say-hello-mbt-b16292ffff06
- Model-based testing: stop writing test cases manually — https://www.testmuai.com/learning-hub/model-based-testing/
- GraphWalker Python — https://github.com/wadle/MBT_GraphWalker_Python
