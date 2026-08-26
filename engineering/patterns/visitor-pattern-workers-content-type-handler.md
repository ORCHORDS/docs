# Visitor Pattern: Workers Content-Type Handler

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

example project serves multiple content types — posts, comments, media attachments, polls, and link previews — each requiring different sanitization, serialization, and validation logic. A single `if/else` chain inside the request handler grows brittle as new content types are added and cross-cuts unrelated concerns (auth, storage, indexing) into one monolith.

## Context

Cloudflare Workers are stateless functions with a 128 MB memory ceiling and tight CPU budgets. Keeping content-type logic in separate, importable visitor classes lets tree-shaking remove handlers that a given Worker route does not need, and makes per-type logic unit-testable without spinning up the entire runtime.

## Pattern Overview — The Visitor Interface

The Visitor pattern separates an algorithm from the object structure it operates on. Each `ContentNode` subtype accepts a `ContentVisitor` and calls the method specific to itself, letting the visitor accumulate results without type-checking.

```typescript
// types/content.ts
export interface ContentVisitor<T> {
  visitPost(node: PostNode): Promise<T>;
  visitComment(node: CommentNode): Promise<T>;
  visitPoll(node: PollNode): Promise<T>;
  visitMediaAttachment(node: MediaNode): Promise<T>;
}

export abstract class ContentNode {
  abstract accept<T>(visitor: ContentVisitor<T>): Promise<T>;
}

export class PostNode extends ContentNode {
  constructor(
    public readonly id: string,
    public readonly body: string,
    public readonly authorHash: string,
    public readonly boardSlug: string,
  ) { super(); }

  accept<T>(visitor: ContentVisitor<T>): Promise<T> {
    return visitor.visitPost(this);
  }
}

export class CommentNode extends ContentNode {
  constructor(
    public readonly id: string,
    public readonly body: string,
    public readonly parentPostId: string,
    public readonly authorHash: string,
  ) { super(); }

  accept<T>(visitor: ContentVisitor<T>): Promise<T> {
    return visitor.visitComment(this);
  }
}

export class PollNode extends ContentNode {
  constructor(
    public readonly id: string,
    public readonly question: string,
    public readonly options: string[],
    public readonly expiresAt: number,
  ) { super(); }

  accept<T>(visitor: ContentVisitor<T>): Promise<T> {
    return visitor.visitPoll(this);
  }
}

export class MediaNode extends ContentNode {
  constructor(
    public readonly id: string,
    public readonly r2Key: string,
    public readonly mimeType: string,
    public readonly byteSize: number,
  ) { super(); }

  accept<T>(visitor: ContentVisitor<T>): Promise<T> {
    return visitor.visitMediaAttachment(this);
  }
}
```

## Implementation — Sanitization Visitor

The sanitization visitor enforces per-type rules (character limits, allowed HTML tags, poll option bounds) without any `instanceof` checks. The return type `SanitizedContent` is a discriminated union consumed downstream.

```typescript
// visitors/sanitize.ts
import { ContentVisitor, PostNode, CommentNode, PollNode, MediaNode } from '../types/content';

export type SanitizedContent =
  | { kind: 'post';    body: string;     boardSlug: string }
  | { kind: 'comment'; body: string;     parentPostId: string }
  | { kind: 'poll';    question: string; options: string[]; expiresAt: number }
  | { kind: 'media';   r2Key: string;    mimeType: string };

const ALLOWED_MIME = new Set(['image/jpeg', 'image/png', 'image/webp', 'video/mp4']);
const MAX_POST_CHARS = 4_000;
const MAX_COMMENT_CHARS = 1_000;
const MAX_POLL_OPTIONS = 6;

export class SanitizationVisitor implements ContentVisitor<SanitizedContent> {
  async visitPost(node: PostNode): Promise<SanitizedContent> {
    const body = node.body.trim().slice(0, MAX_POST_CHARS);
    if (!body) throw new Error('Post body is empty after sanitization');
    return { kind: 'post', body, boardSlug: node.boardSlug };
  }

  async visitComment(node: CommentNode): Promise<SanitizedContent> {
    const body = node.body.trim().slice(0, MAX_COMMENT_CHARS);
    if (!body) throw new Error('Comment body is empty after sanitization');
    return { kind: 'comment', body, parentPostId: node.parentPostId };
  }

  async visitPoll(node: PollNode): Promise<SanitizedContent> {
    const options = node.options.map(o => o.trim()).filter(Boolean).slice(0, MAX_POLL_OPTIONS);
    if (options.length < 2) throw new Error('Poll requires at least 2 options');
    const question = node.question.trim().slice(0, 280);
    return { kind: 'poll', question, options, expiresAt: node.expiresAt };
  }

  async visitMediaAttachment(node: MediaNode): Promise<SanitizedContent> {
    if (!ALLOWED_MIME.has(node.mimeType)) {
      throw new Error(`Unsupported MIME type: ${node.mimeType}`);
    }
    if (node.byteSize > 50 * 1024 * 1024) throw new Error('File exceeds 50 MB limit');
    return { kind: 'media', r2Key: node.r2Key, mimeType: node.mimeType };
  }
}
```

## Workers Integration — Request Dispatcher

The Worker entry point deserializes the request body into a `ContentNode` and feeds it to whichever visitors the route requires. Visitors compose without coupling; a new `IndexingVisitor` added later touches zero existing code.

```typescript
// worker.ts
import { PostNode, CommentNode, PollNode, MediaNode } from './types/content';
import { SanitizationVisitor } from './visitors/sanitize';

interface Env {
  DB: D1Database;
  CONTENT_BUCKET: R2Bucket;
}

function parseNode(body: Record<string, unknown>) {
  switch (body.type) {
    case 'post':
      return new PostNode(
        crypto.randomUUID(),
        body.body as string,
        body.authorHash as string,
        body.boardSlug as string,
      );
    case 'comment':
      return new CommentNode(
        crypto.randomUUID(),
        body.body as string,
        body.parentPostId as string,
        body.authorHash as string,
      );
    case 'poll':
      return new PollNode(
        crypto.randomUUID(),
        body.question as string,
        body.options as string[],
        body.expiresAt as number,
      );
    default:
      throw new Error(`Unknown content type: ${body.type}`);
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') {
      return new Response('Method Not Allowed', { status: 405 });
    }

    let raw: Record<string, unknown>;
    try {
      raw = await request.json();
    } catch {
      return new Response('Invalid JSON', { status: 400 });
    }

    try {
      const node = parseNode(raw);
      const sanitizer = new SanitizationVisitor();
      const clean = await node.accept(sanitizer);

      // Further visitors (scoring, indexing) added here without modifying parseNode
      return Response.json({ ok: true, data: clean }, { status: 201 });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Unknown error';
      return new Response(JSON.stringify({ ok: false, error: msg }), {
        status: 422,
        headers: { 'Content-Type': 'application/json' },
      });
    }
  },
};
```

## Anti-patterns

- Switching on `instanceof` inside the Worker handler — defeats tree-shaking and centralises type knowledge
- Adding mutable state to visitor instances shared across requests — Workers may re-use module scope; visitors should be stateless or instantiated per-request
- Throwing generic `Error` without a structured code — callers cannot distinguish validation from infrastructure failures
- Putting I/O (D1 writes, R2 puts) directly inside `visitPost` — visitors should return data; a separate persistence layer receives the sanitized result

## Gotchas

- `crypto.randomUUID()` is available in the Workers runtime without importing `node:crypto`
- TypeScript discriminated unions on `SanitizedContent.kind` let downstream consumers narrow without casting
- Poll `expiresAt` should be validated as a Unix timestamp in the future; the visitor above omits this for brevity — add a wall-clock check via `Date.now()`
- Workers bundle size matters: if a route never handles polls, import only the needed visitor to avoid shipping dead code

## Verification

```bash
# Unit test each visitor in isolation using vitest + @cloudflare/vitest-pool-workers
npx vitest run src/visitors/sanitize.test.ts

# Integration: POST to local wrangler dev endpoint
curl -X POST http://localhost:8787/content \
  -H 'Content-Type: application/json' \
  -d '{"type":"post","body":"Hello example project","authorHash":"abc123","boardSlug":"general"}'
# Expect: {"ok":true,"data":{"kind":"post","body":"Hello example project","boardSlug":"general"}}
```

## Related

- `decorator-pattern-workers-middleware-composition.md` — layering cross-cutting concerns around handlers
- `null-object-pattern-workers-default-handler.md` — fallback when no matching type is found
- `template-method-pattern-workers-handler.md` — base handler skeleton with per-type overrides
- `specification-pattern-d1-query-building.md` — composable predicates for content filtering

## Sources

- https://www.cloudflare.com/developer-platform/workers/
- https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
- https://refactoring.guru/design-patterns/visitor
- https://developers.cloudflare.com/workers/testing/vitest-integration/
