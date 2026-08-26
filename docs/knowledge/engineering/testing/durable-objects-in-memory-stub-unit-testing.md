# Durable Object Unit Testing with In-Memory Stub Implementations

2026-08-24 / example.com / production

---

## Symptom / Use-case

Your Worker delegates state management to a Durable Object but the unit tests start Miniflare for every test file, adding 2-4 seconds of cold-start overhead per suite. Alternatively, you want to test the Worker's orchestration logic in complete isolation — verifying that it calls the right DO methods with the right arguments — without spinning up any runtime infrastructure at all.

Writing a hand-rolled TypeScript stub that implements the `DurableObjectStub` interface gives you zero-overhead, deterministic, introspectable fakes you can assert on directly.

---

## Context

Cloudflare's `DurableObjectStub` is the RPC handle a Worker receives from `env.MY_DO.get(id)`. Its surface consists of `fetch()` for HTTP-over-DO and, with Workers RPC enabled, arbitrary method calls via Proxy. A stub implementation replaces the real binding in unit tests by satisfying the same TypeScript interface the production code calls.

This approach is suitable when:
- You want to test the *Worker* layer (routing, auth, transformation) without testing the DO storage layer.
- The DO's methods are complex enough to have their own test suite, making mixed tests redundant.
- Test suites must run in a standard Node environment without `@cloudflare/vitest-pool-workers`.

The stub pattern complements, rather than replaces, Miniflare integration tests: stubs validate the Worker's contract with the DO; Miniflare tests validate the DO's contract with SQLite/DurableObjectStorage.

---

## Defining the Stub Interface

```ts
// test/stubs/durable-object-stub.ts
import type { DurableObjectId, DurableObjectStub } from "@cloudflare/workers-types";

/**
 * Minimal in-memory DurableObjectStub that tracks calls for assertion.
 * Extend with test-specific state as needed.
 */
export class InMemoryDurableObjectStub implements DurableObjectStub {
  readonly id: DurableObjectId;
  readonly name: string | undefined;

  private _calls: Array<{ method: string; args: unknown[] }> = [];
  private _fetchHandler: (req: Request) => Promise<Response>;

  constructor(
    id: DurableObjectId,
    fetchHandler: (req: Request) => Promise<Response> = async () =>
      new Response(JSON.stringify({ ok: true }), {
        headers: { "Content-Type": "application/json" },
      }),
  ) {
    this.id = id;
    this._fetchHandler = fetchHandler;
  }

  async fetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
    const req = input instanceof Request ? input : new Request(input, init);
    this._calls.push({ method: "fetch", args: [req.url, req.method] });
    return this._fetchHandler(req);
  }

  /** Inspect recorded fetch calls in test assertions. */
  get calls() {
    return this._calls as ReadonlyArray<{ method: string; args: unknown[] }>;
  }

  resetCalls() {
    this._calls = [];
  }
}
```

---

## Stubbing a Durable Object Namespace Binding

The binding (`env.MY_DO`) is a `DurableObjectNamespace`. Stub it so `get()` returns your `InMemoryDurableObjectStub`.

```ts
// test/stubs/durable-object-namespace.ts
import type {
  DurableObjectId,
  DurableObjectNamespace,
  DurableObjectStub,
} from "@cloudflare/workers-types";
import { InMemoryDurableObjectStub } from "./durable-object-stub";

export class InMemoryDurableObjectNamespace implements DurableObjectNamespace {
  private _instances = new Map<string, InMemoryDurableObjectStub>();
  private _idCounter = 0;

  newUniqueId(_opts?: { jurisdiction?: string }): DurableObjectId {
    const raw = String(++this._idCounter).padStart(64, "0");
    return this._makeId(raw);
  }

  idFromName(name: string): DurableObjectId {
    return this._makeId(name.padEnd(64, "0").slice(0, 64));
  }

  idFromString(id: string): DurableObjectId {
    return this._makeId(id);
  }

  get(id: DurableObjectId, _opts?: unknown): DurableObjectStub {
    const key = id.toString();
    if (!this._instances.has(key)) {
      this._instances.set(key, new InMemoryDurableObjectStub(id));
    }
    return this._instances.get(key)!;
  }

  jurisdiction(_j: string): DurableObjectNamespace {
    return this;
  }

  getStub(id: DurableObjectId): InMemoryDurableObjectStub | undefined {
    return this._instances.get(id.toString());
  }

  private _makeId(raw: string): DurableObjectId {
    return {
      toString: () => raw,
      equals: (other: DurableObjectId) => other.toString() === raw,
      name: undefined,
    } as DurableObjectId;
  }
}
```

---

## Configuring a Fake Fetch Response

Override the `fetchHandler` in the stub constructor to control per-instance behavior in specific test cases.

```ts
// test/stubs/helpers.ts
import { InMemoryDurableObjectStub } from "./durable-object-stub";
import type { DurableObjectId } from "@cloudflare/workers-types";

export function stubWithResponse(
  id: DurableObjectId,
  body: unknown,
  status = 200,
): InMemoryDurableObjectStub {
  return new InMemoryDurableObjectStub(id, async () =>
    Response.json(body, { status }),
  );
}

export function stubWithError(id: DurableObjectId): InMemoryDurableObjectStub {
  return new InMemoryDurableObjectStub(id, async () =>
    Response.json({ error: "Internal error" }, { status: 500 }),
  );
}
```

---

## Unit Test: Worker Delegation Behaviour

```ts
// test/unit/cart-worker.test.ts
import { describe, it, expect, beforeEach } from "vitest";
import { InMemoryDurableObjectNamespace } from "../stubs/durable-object-namespace";
import worker from "../../src/cart-worker";

let doNamespace: InMemoryDurableObjectNamespace;

beforeEach(() => {
  doNamespace = new InMemoryDurableObjectNamespace();
});

function makeEnv() {
  return { CART: doNamespace } as unknown as Env;
}

describe("POST /cart/:userId/items", () => {
  it("delegates to the correct Durable Object by userId", async () => {
    const res = await worker.fetch(
      new Request("https://worker.test/cart/user-42/items", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ productId: "sku-9", qty: 2 }),
      }),
      makeEnv(),
    );

    expect(res.status).toBe(200);

    const id = doNamespace.idFromName("user-42");
    const stub = doNamespace.getStub(id)!;
    expect(stub.calls).toHaveLength(1);
    expect(stub.calls[0].args).toContain(
      "https://do.internal/items",
    );
  });

  it("surfaces 500 from DO as 502 to the client", async () => {
    // Pre-register a stub that always errors
    const id = doNamespace.idFromName("user-bad");
    // inject error stub directly into the namespace's instance map
    (doNamespace as unknown as { _instances: Map<string, unknown> })._instances.set(
      id.toString(),
      { id, fetch: async () => new Response("DO error", { status: 500 }), calls: [] },
    );

    const res = await worker.fetch(
      new Request("https://worker.test/cart/user-bad/items", {
        method: "POST",
        body: JSON.stringify({ productId: "x", qty: 1 }),
        headers: { "Content-Type": "application/json" },
      }),
      makeEnv(),
    );

    expect(res.status).toBe(502);
  });
});
```

---

## RPC Stubs with Workers RPC

For Durable Objects that expose typed RPC methods (via `extends DurableObject` class with public methods), create a matching TypeScript interface and stub:

```ts
// src/cart-do-rpc.ts (type export from the DO module)
export interface CartDORPC {
  addItem(productId: string, qty: number): Promise<{ total: number }>;
  clearCart(): Promise<void>;
}

// test/stubs/cart-do-rpc-stub.ts
import type { CartDORPC } from "../../src/cart-do-rpc";

export class CartDORPCStub implements CartDORPC {
  items: Array<{ productId: string; qty: number }> = [];

  async addItem(productId: string, qty: number) {
    this.items.push({ productId, qty });
    return { total: this.items.length };
  }

  async clearCart() {
    this.items = [];
  }
}
```

```ts
// test/unit/cart-rpc.test.ts
import { describe, it, expect } from "vitest";
import { CartDORPCStub } from "../stubs/cart-do-rpc-stub";

describe("CartDORPCStub", () => {
  it("tracks added items", async () => {
    const stub = new CartDORPCStub();
    const result = await stub.addItem("sku-1", 3);
    expect(result).toEqual({ total: 1 });
    expect(stub.items).toEqual([{ productId: "sku-1", qty: 3 }]);
  });
});
```

---

## Anti-patterns

- **Faithfully re-implementing DO storage logic in the stub** — the stub should capture *calls*, not reproduce storage; test the real DO separately with Miniflare.
- **Sharing a single stub instance across tests** — DO instances are keyed by ID; use `beforeEach` to reset or recreate the namespace.
- **Casting env as `any`** — type the stub to the generated `Env` type; cast once at the `makeEnv()` boundary and nowhere else.
- **Stubbing the global `fetch`** — Workers communicate with DOs via the binding, not global `fetch`; stub at the namespace layer, not the network layer.
- **Omitting error path stubs** — real DOs can return 5xx; always test the Worker's handling of DO failures.

---

## Gotchas

- `DurableObjectId.toString()` must return a 64-character hex string in production; in stubs any unique string works as a map key, but if code calls `idFromString` with a stub-generated ID, ensure the same format is used throughout.
- Workers RPC proxies are created at runtime by the CF runtime's Proxy machinery; TypeScript interface stubs only validate the interface, not the wire protocol. Always back them with Miniflare RPC tests for protocol-level confidence.
- If the Worker uses `stub.fetch` with a relative URL (e.g., `new Request("/items", …)`), the stub may receive a malformed URL without a scheme; always construct absolute URLs when calling DO fetch.
- The stub's `calls` array captures arguments *before* the fake handler runs; if the handler throws, the call is still recorded.

---

## Verification

```bash
# Run in Node without the Workers pool (no wrangler needed)
npx vitest run test/unit --reporter=verbose

# Confirm no Miniflare dependency in the unit test layer
grep -r "miniflare\|wrangler" test/unit/ && echo "found" || echo "clean"
```

Expected: unit tests complete in under 500 ms total with zero Miniflare processes spawned.

---

## Related

- `vitest-durable-objects-rpc-testing.md` — RPC testing with Miniflare pool workers
- `vitest-durable-objects-storage-reset-isolation.md` — storage isolation strategies
- `durable-objects-alarm-testing-miniflare.md` — alarm testing with real runtime
- `test-doubles-cloudflare-workers.md` — broader doubles taxonomy for Workers
- `mocking-vs-stubbing-vs-spying.md` — conceptual distinctions

---

## Sources

- Durable Objects RPC: https://developers.cloudflare.com/durable-objects/api/rpc/
- `@cloudflare/workers-types` DurableObject interfaces: https://github.com/cloudflare/workers-types
- Vitest: https://vitest.dev/guide/mocking.html
