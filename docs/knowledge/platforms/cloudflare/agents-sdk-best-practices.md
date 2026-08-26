# agents-sdk-best-practices

**Issue:** Cloudflare Agents SDK — durable agent runtime
**Date:** 2026-08-09
**Status:** documented

## Symptom
You build an AI agent. The agent loses context
between turns. The agent can't call tools. The agent
isn't durable across requests. You wish you had a
runtime for agents.

## Root cause
**Agents need a runtime.** Use CF Agents SDK.

**Source:** Agents SDK:
https://developers.cloudflare.com/agents/

## The "Agents SDK" concept

The Agents SDK is a runtime for AI agents:
- **Durable identity:** Per session
- **Local SQL storage:** Per agent
- **Real-time:** WebSocket
- **Scheduled work:** Alarms
- **Recoverable:** Survives failures
- **MCP support:** Tool calling
- **Code Mode:** Orchestrate multiple tools

The agent is durable.

## The "Agent" class pattern

For an Agent:
```ts
import { Agent } from 'agents';

export class MyAgent extends Agent<Env, State> {
  initialState = { messages: [] };

  async onStart() {
    // Called when the agent starts
    console.log('Agent started');
  }

  async onMessage(message: string) {
    // Called when a message is received
    const response = await this.env.AI.run('@cf/meta/llama-2-7b-chat-int8', {
      prompt: message,
    });

    this.setState({
      ...this.state,
      messages: [...this.state.messages, { role: 'user', content: message }, { role: 'assistant', content: response.response }],
    });
  }
}
```

The agent is defined.

## The "binding" pattern

For the binding:
```toml
[[durable_objects.bindings]]
name = "AGENT"
class_name = "MyAgent"

[[migrations]]
tag = "v1"
new_sqlite_classes = ["MyAgent"]
```

The agent is bound.

## The "create" pattern

For creating an agent:
```ts
const id = env.AGENT.idFromName('user_123');
const stub = env.AGENT.get(id);
const response = await stub.fetch('https://agent/message', {
  method: 'POST',
  body: JSON.stringify({ message: 'Hello' }),
});
```

The agent is fetched.

## The "WebSocket" pattern

For real-time:
```ts
export class MyAgent extends Agent<Env, State> {
  async onConnect(connection: Connection) {
    connection.accept();
  }

  async onMessage(connection: Connection, message: string) {
    // Process
    const response = await this.env.AI.run('@cf/meta/llama-2-7b-chat-int8', { prompt: message });
    connection.send(JSON.stringify({ response: response.response }));
  }
}
```

The agent is real-time.

## The "scheduled work" pattern

For scheduled:
```ts
export class MyAgent extends Agent<Env, State> {
  async onStart() {
    // Schedule every 5 min
    setInterval(async () => {
      await this.runDailyDigest();
    }, 5 * 60 * 1000);
  }
}
```

The agent is scheduled.

## The "state" pattern

For state:
```ts
interface State {
  messages: Array<{ role: string; content: string }>;
  userId: string;
  preferences: Record<string, any>;
}

this.setState({ ...this.state, messages: [...this.state.messages, newMessage] });
```

The state is mutable + persistent.

## The "MCP" pattern

For MCP tools:
```ts
import { McpAgent } from 'agents/mcp';

export class MyMcpAgent extends McpAgent<Env> {
  async init() {
    // Add MCP servers
    this.addMcpServer('my-server', env.MY_MCP_SERVER);
  }

  async onRequest(request: Request): Promise<Response> {
    return this.handleMcpRequest(request);
  }
}
```

The agent has MCP tools.

## The "Code Mode" pattern

For Code Mode (multiple tools):
```ts
import { CodeMode } from '@cloudflare/codemode';

export class MyAgent extends Agent<Env, State> {
  async onMessage(message: string) {
    // Code Mode runs the code in a sandbox
    const result = await CodeMode.execute(`
      const user = await searchUsers({ query: '${message}' });
      return user;
    `);

    return result;
  }
}
```

The agent orchestrates tools via code.

## The "AI Search" pattern

For AI Search (built-in):
```ts
const results = await this.env.AI_SEARCH.search('my-index', {
  query: 'find similar documents',
  topK: 5,
});
```

The search is built-in.

## The "agent hibernation" pattern

For hibernation (save resources):
```ts
this.ctx.waitUntil(
  (async () => {
    // Long work
    await this.expensiveWork();
  })()
);
```

The agent hibernates.

## The "agent observability" pattern

For observability:
- **Trace:** Per agent turn
- **Tokens:** Per model call
- **Tool calls:** Per turn
- **Errors:** Per agent

```ts
// In the dashboard
// Workers Observability shows agent traces
```

The agent is observable.

## The "Agents SDK limits" pattern

For limits:
- **Concurrent agents:** Per plan
- **State size:** 128KB per agent
- **Storage:** 10GB per agent
- **WebSocket:** 32k per agent

The limits are checked.

## The "agent anti-pattern" anti-patterns

### 1. No state
- **Issue:** Agent loses context
- **Fix:** setState

### 2. No tools
- **Issue:** Agent is just a chat
- **Fix:** MCP tools

### 3. No durability
- **Issue:** Agent loses data
- **Fix:** DO state

### 4. No hibernation
- **Issue:** Always-on cost
- **Fix:** Hibernation

### 5. No observability
- **Issue:** Can't debug
- **Fix:** Observability

## Verification
- **Test:** Agent runs
- **Test:** State persists
- **Test:** MCP tools work
- **Test:** WebSocket works
- **Live:** Agent monitored
- **Audit:** Quarterly review

## Gotchas
- **The "no state" anti-pattern.** setState.
- **The "no tools" anti-pattern.** MCP tools.
- **The "no hibernation" anti-pattern.** Hibernate.

## Related
- `cloudflare/durable-objects-best-practices.md`
- `cloudflare/workflows-best-practices.md`
- `cloudflare/ai-gateway-best-practices.md`
- `feature-cookbook-ai-ml-detail.md`
- Agents SDK: https://developers.cloudflare.com/agents/
- @cloudflare/think: https://www.npmjs.com/package/@cloudflare/think
- @cloudflare/codemode: https://www.npmjs.com/package/@cloudflare/codemode
