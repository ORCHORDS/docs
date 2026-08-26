# Cloudflare Workflows: Human-in-the-Loop Approval Patterns

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
An automated process — such as a deployment pipeline, a refund request, or a content moderation action — needs a human to approve or reject it before the Workflow continues, with the pause potentially lasting hours or days.

## Context
Cloudflare Workflows (in open beta as of mid-2025) support durable multi-step execution where each step's output is checkpointed to storage. A human-in-the-loop approval gate is implemented by pausing the Workflow with `step.waitForEvent()`, which suspends execution and releases the Worker's CPU. An external actor — an email link, a Slack slash command, or a dashboard button — calls back into the Workflow via an HTTP trigger that resumes it with an approval decision. The Workflow does not consume CPU while waiting, and it automatically resumes after the callback arrives or a timeout fires.

## Defining the Workflow with an Approval Gate

```typescript
// workflows/approval-workflow.ts
import {
  WorkflowEntrypoint,
  WorkflowStep,
  WorkflowEvent,
} from "cloudflare:workers";

export interface ApprovalPayload {
  requestId: string;
  tenantId: string;
  action: string;
  requestedBy: string;
  details: Record<string, unknown>;
}

export interface ApprovalDecision {
  approved: boolean;
  reviewerId: string;
  comment?: string;
  decidedAt: string;
}

export interface Env {
  APPROVAL_WORKFLOW: Workflow;
  DB: D1Database;
  EMAIL: SendEmail; // optional email routing binding
}

export class ApprovalWorkflow extends WorkflowEntrypoint<Env, ApprovalPayload> {
  async run(event: WorkflowEvent<ApprovalPayload>, step: WorkflowStep) {
    const { requestId, tenantId, action, requestedBy, details } = event.payload;

    // Step 1: Persist the pending request to D1
    await step.do("persist-request", async () => {
      await this.env.DB.prepare(
        `INSERT INTO approval_requests (id, tenant_id, action, requested_by, details, status, created_at)
         VALUES (?, ?, ?, ?, ?, 'pending', ?)`
      )
        .bind(requestId, tenantId, action, requestedBy, JSON.stringify(details), Date.now())
        .run();
    });

    // Step 2: Send notification to reviewer (email, Slack, etc.)
    await step.do("notify-reviewer", async () => {
      await sendApprovalEmail(requestId, action, requestedBy);
    });

    // Step 3: Pause and wait for approval — up to 7 days
    const decision = await step.waitForEvent<ApprovalDecision>(
      "approval-decision",
      {
        timeout: "7 days",
      }
    );

    // Step 4: Record the decision
    await step.do("record-decision", async () => {
      await this.env.DB.prepare(
        `UPDATE approval_requests
         SET status = ?, reviewer_id = ?, comment = ?, decided_at = ?
         WHERE id = ?`
      )
        .bind(
          decision.approved ? "approved" : "rejected",
          decision.reviewerId,
          decision.comment ?? null,
          decision.decidedAt,
          requestId
        )
        .run();
    });

    // Step 5: Execute the approved action or notify rejection
    if (decision.approved) {
      await step.do("execute-action", async () => {
        await executeApprovedAction(action, details);
      });
    } else {
      await step.do("notify-rejection", async () => {
        await notifyRequester(requestedBy, requestId, decision.comment);
      });
    }

    return {
      requestId,
      outcome: decision.approved ? "approved" : "rejected",
      reviewerId: decision.reviewerId,
    };
  }
}

// Stub helpers — implement with your email/webhook provider
async function sendApprovalEmail(
  requestId: string,
  action: string,
  requestedBy: string
): Promise<void> {
  console.log(`Sending approval email for ${requestId}: ${action} by ${requestedBy}`);
  // Construct approval URL with signed token, send via Email Routing or fetch()
}

async function executeApprovedAction(
  action: string,
  details: Record<string, unknown>
): Promise<void> {
  console.log(`Executing action: ${action}`, details);
}

async function notifyRequester(
  requestedBy: string,
  requestId: string,
  comment?: string
): Promise<void> {
  console.log(`Notifying ${requestedBy}: request ${requestId} rejected. Reason: ${comment}`);
}
```

## Triggering the Workflow and Sending the Callback

The main Worker creates a Workflow instance and provides the callback endpoint for reviewers.

```typescript
// worker.ts
export interface Env {
  APPROVAL_WORKFLOW: Workflow;
  DB: D1Database;
  SIGNING_SECRET: string; // secret for HMAC-signed approval tokens
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // POST /workflows/approvals — create a new approval request
    if (url.pathname === "/workflows/approvals" && request.method === "POST") {
      const body = await request.json<ApprovalPayload>();
      const instance = await env.APPROVAL_WORKFLOW.create({
        id: body.requestId,
        params: body,
      });
      return Response.json({ instanceId: instance.id, status: "pending" });
    }

    // POST /workflows/approvals/:id/decide — reviewer submits decision
    const match = url.pathname.match(/^\/workflows\/approvals\/([^/]+)\/decide$/);
    if (match && request.method === "POST") {
      const requestId = match[1];
      const decision = await request.json<ApprovalDecision & { token: string }>();

      // Validate HMAC token to prevent unauthorized approvals
      const valid = await verifyApprovalToken(
        env.SIGNING_SECRET,
        requestId,
        decision.token
      );
      if (!valid) return new Response("Forbidden", { status: 403 });

      // Resume the waiting Workflow with the decision
      const instance = await env.APPROVAL_WORKFLOW.get(requestId);
      await instance.sendEvent({
        type: "approval-decision",
        payload: {
          approved: decision.approved,
          reviewerId: decision.reviewerId,
          comment: decision.comment,
          decidedAt: new Date().toISOString(),
        },
      });

      return Response.json({ ok: true, requestId, approved: decision.approved });
    }

    return new Response("Not found", { status: 404 });
  },
};

async function verifyApprovalToken(
  secret: string,
  requestId: string,
  token: string
): Promise<boolean> {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["verify"]
  );
  const expected = await crypto.subtle.sign(
    "HMAC",
    key,
    new TextEncoder().encode(requestId)
  );
  const expectedHex = [...new Uint8Array(expected)]
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
  return expectedHex === token;
}
```

## Timeout Handling and Expiry

When `waitForEvent` times out without receiving an event, the Workflow receives an error that you handle in the step.

```typescript
// Inside the run() method, replacing the simple waitForEvent call:
let decision: ApprovalDecision;
try {
  decision = await step.waitForEvent<ApprovalDecision>("approval-decision", {
    timeout: "7 days",
  });
} catch (err) {
  // Timeout — auto-reject or escalate
  await step.do("handle-timeout", async () => {
    await this.env.DB.prepare(
      `UPDATE approval_requests SET status = 'expired' WHERE id = ?`
    ).bind(event.payload.requestId).run();
  });
  return { requestId: event.payload.requestId, outcome: "expired" };
}
```

## Wrangler Configuration

```toml
# wrangler.toml
name = "approval-worker"
compatibility_date = "2026-01-01"
compatibility_flags = ["nodejs_compat"]

[[workflows]]
name = "approval-workflow"
binding = "APPROVAL_WORKFLOW"
class_name = "ApprovalWorkflow"

[[d1_databases]]
binding = "DB"
database_name = "approvals-db"
database_id = "<your-db-id>"
```

## Anti-patterns
- Polling D1 or KV in a loop inside a Workflow step to wait for approval — `waitForEvent` is the correct primitive; polling consumes CPU budget and does not survive Worker restarts
- Using a plain KV flag as the resume mechanism — Workflows checkpoint durably; resuming via `sendEvent()` is the only guaranteed way to deliver data into the paused step
- Putting approval logic inside `step.do()` after `waitForEvent()` without a try/catch — a timeout arrives as a thrown error if no event is received within the window
- Signing tokens with the `requestId` alone without a nonce — add a `validUntil` field to the token payload to prevent replay attacks on expired requests

## Gotchas
- `workflow.get(id)` throws if the instance does not exist; wrap in try/catch to return a 404 to the client
- `waitForEvent` timeout strings use human-readable durations (`"7 days"`, `"2 hours"`, `"30 minutes"`); they are not ISO 8601 durations
- A Workflow instance ID must be globally unique within the binding; using the `requestId` directly is safe only if it is already a UUID or ULID
- Sending an event to a Workflow that has already completed or timed out silently fails — always check instance status before calling `sendEvent`

## Verification
1. POST to `/workflows/approvals` with a valid payload and confirm a Workflow instance is created
2. Check D1 that the request row has `status = 'pending'`
3. POST to `/workflows/approvals/:id/decide` with `approved: true` and a valid HMAC token
4. Confirm D1 row updates to `status = 'approved'` and `decided_at` is populated
5. Start a second instance, wait for the 30-second test timeout, and confirm the row transitions to `status = 'expired'` without a decision event

## Related
- `workflows-2026.md`
- `workflows-best-practices.md`
- `durable-objects-alarms-scheduling.md`
- `workers-crypto-patterns.md`
- `d1-best-practices.md`

## Sources
- https://developers.cloudflare.com/workflows/
- https://developers.cloudflare.com/workflows/reference/events-and-callbacks/
- https://developers.cloudflare.com/workflows/configuration/timeouts/
