# Pulumi Dynamic Provider for Cloudflare Custom Resources

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to manage a Cloudflare resource — such as an Account Ruleset override, a Logpush ownership challenge, or a custom Hostname fallback origin — that is not yet exposed by the official `@pulumi/cloudflare` package, without forking the provider or writing a Go plugin.

## Context

Pulumi's dynamic provider lets you implement `create`, `read`, `update`, `delete`, and `diff` lifecycle methods in TypeScript inside your Pulumi program. Dynamic providers are slower than compiled providers but are ideal for one-off Cloudflare API resources and rapid prototyping.

---

## Dynamic Provider Base Pattern

```typescript
// lib/cloudflare-dynamic.ts
import * as pulumi from "@pulumi/pulumi";

const CF_API = "https://api.cloudflare.com/client/v4";

export async function cfFetch(method: string, path: string, token: string, body?: unknown): Promise<unknown> {
  const res = await fetch(`${CF_API}${path}`, {
    method,
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  const json = (await res.json()) as { success: boolean; result: unknown; errors: unknown[] };
  if (!json.success) throw new Error(`Cloudflare API error: ${JSON.stringify(json.errors)}`);
  return json.result;
}
```

## Custom Resource: Account-Level Ruleset Phase Override

```typescript
// resources/account-ruleset-override.ts
interface AccountRulesetInputs {
  accountId: string; apiToken: string; phase: string; description: string; rules: object[];
}

const accountRulesetProvider: pulumi.dynamic.ResourceProvider = {
  async create(inputs: AccountRulesetInputs) {
    const result = (await cfFetch("POST", `/accounts/${inputs.accountId}/rulesets`, inputs.apiToken,
      { phase: inputs.phase, description: inputs.description, rules: inputs.rules, kind: "root" }
    )) as { id: string };
    return { id: result.id, outs: { ...inputs, rulesetId: result.id } };
  },

  async read(id: string, props: AccountRulesetInputs & { rulesetId: string }) {
    const result = (await cfFetch("GET", `/accounts/${props.accountId}/rulesets/${id}`, props.apiToken)) as { id: string; phase: string; description: string; rules: object[] };
    return { id, props: { ...props, rulesetId: result.id } };
  },

  async update(id: string, _olds: AccountRulesetInputs, news: AccountRulesetInputs) {
    await cfFetch("PUT", `/accounts/${news.accountId}/rulesets/${id}`, news.apiToken, { description: news.description, rules: news.rules });
    return { outs: { ...news, rulesetId: id } };
  },

  async delete(id: string, props: AccountRulesetInputs) {
    await cfFetch("DELETE", `/accounts/${props.accountId}/rulesets/${id}`, props.apiToken);
  },

  async diff(id: string, olds: AccountRulesetInputs, news: AccountRulesetInputs) {
    const changedKeys: string[] = [];
    if (JSON.stringify(olds.rules) !== JSON.stringify(news.rules)) changedKeys.push("rules");
    if (olds.description !== news.description) changedKeys.push("description");
    return { changes: changedKeys.length > 0, replaces: [], stables: ["phase"] };
  },
};

export class AccountRulesetOverride extends pulumi.dynamic.Resource {
  public readonly rulesetId!: pulumi.Output<string>;

  constructor(name: string, args: AccountRulesetInputs, opts?: pulumi.CustomResourceOptions) {
    super(accountRulesetProvider, name, { ...args, rulesetId: undefined }, opts);
  }
}
```

## Wiring into a Pulumi Stack

```typescript
// index.ts
const config = new pulumi.Config("cloudflare");
const accountId = config.require("accountId");
const apiToken  = <redacted-secret>"apiToken");

const ruleset = new AccountRulesetOverride("managed-cf-ruleset", {
  accountId,
  apiToken: apiToken as unknown as string,
  phase: "http_request_firewall_managed",
  description: "Enable Cloudflare Managed Rules",
  rules: [{
    action: "execute",
    expression: "true",
    action_parameters: { id: "efb7b8c949ac4650a09736fc376e9aee" },
    description: "Execute Cloudflare Managed Ruleset",
  }],
});

export const rulesetId = ruleset.rulesetId;
```

## Anti-patterns

- Storing `apiToken` in `outs` without relying on Pulumi's secret config system.
- Omitting `diff()` — Pulumi will call `update()` on every deploy.
- Using dynamic providers for resources the official package already covers.

## Gotchas

- Dynamic provider code runs in the Pulumi automation context, not the Worker runtime.
- If you rename the dynamic provider class, Pulumi treats it as a new resource type.
- Dynamic providers are serialized to JSON — closures that capture module-level state will fail.

## Verification

```bash
pulumi stack export | jq '.deployment.resources[] | select(.type | contains("dynamic"))'

curl -s "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/rulesets" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '.result[] | {id, phase, description}'

pulumi refresh --yes
```

## Related

- `pulumi-cloudflare-provider-advanced.md`
- `pulumi-cloudflare-workers-infrastructure-as-code.md`

## Sources

- https://www.pulumi.com/docs/concepts/resources/dynamic-providers/
- https://developers.cloudflare.com/ruleset-engine/rulesets-api/
