# Abstract Factory Pattern — Workers Provider Switching

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A Worker integrates with a third-party service — email, SMS, object storage, AI
inference — and you want to swap providers without touching business logic. You also
need to run a stub in local `wrangler dev` without hitting live APIs, and a different
provider in EU to comply with data-residency rules. Every time you add an `if (env
=== 'prod')` fork into the handler, the code gets harder to test and reason about.

## Context

The Abstract Factory pattern defines an interface for creating families of related
objects, then lets subclasses (or factory implementations) decide which concrete classes
to instantiate. In a Worker the "factory" is typically instantiated once at module scope
from `env` bindings, then handed to every handler. Because Workers have no DI container,
the factory is simply a TypeScript interface that each provider implements, constructed
by a single factory-selector function keyed on an env variable.

## Provider Interface

Define what every provider in a family must support. Keep it minimal.

```typescript
// providers/email.ts
export interface EmailMessage {
  to: string;
  subject: string;
  text: string;
  html?: string;
}

export interface EmailProvider {
  send(msg: EmailMessage): Promise<{ id: string }>;
}

// providers/sms.ts
export interface SmsMessage {
  to: string;   // E.164 format
  body: string;
}

export interface SmsProvider {
  send(msg: SmsMessage): Promise<{ sid: string }>;
}
```

## Concrete Provider Implementations

```typescript
// providers/email-sendgrid.ts
import type { EmailProvider, EmailMessage } from './email';

export class SendGridEmailProvider implements EmailProvider {
  constructor(private readonly apiKey: string) {}

  async send(msg: EmailMessage): Promise<{ id: string }> {
    const res = await fetch('https://api.sendgrid.com/v3/mail/send', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${this.apiKey}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        personalizations: [{ to: [{ email: msg.to }] }],
        from: { email: 'noreply@example.com' },
        subject: msg.subject,
        content: [{ type: 'text/plain', value: msg.text }],
      }),
    });
    const xMessageId = res.headers.get('x-message-id') ?? crypto.randomUUID();
    if (!res.ok) throw new Error(`SendGrid error ${res.status}`);
    return { id: xMessageId };
  }
}

// providers/email-resend.ts
import type { EmailProvider, EmailMessage } from './email';

export class ResendEmailProvider implements EmailProvider {
  constructor(private readonly apiKey: string) {}

  async send(msg: EmailMessage): Promise<{ id: string }> {
    const res = await fetch('https://api.resend.com/emails', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${this.apiKey}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        from: 'noreply@example.com',
        to: msg.to,
        subject: msg.subject,
        text: msg.text,
        html: msg.html,
      }),
    });
    const { id } = await res.json<{ id: string }>();
    return { id };
  }
}

// providers/email-stub.ts  (used in wrangler dev / unit tests)
import type { EmailProvider, EmailMessage } from './email';

export class StubEmailProvider implements EmailProvider {
  public readonly sent: EmailMessage[] = [];

  async send(msg: EmailMessage): Promise<{ id: string }> {
    this.sent.push(msg);
    console.log('[StubEmail]', msg.to, msg.subject);
    return { id: `stub-${Date.now()}` };
  }
}
```

## Abstract Factory Interface and Selector

```typescript
// factory.ts
import type { EmailProvider } from './providers/email';
import type { SmsProvider }   from './providers/sms';

export interface NotificationFactory {
  email(): EmailProvider;
  sms(): SmsProvider;
}

export interface Env {
  PROVIDER:      string;   // "sendgrid" | "resend" | "stub"
  SENDGRID_KEY:  string;
  RESEND_KEY:    string;
}

export function createNotificationFactory(env: Env): NotificationFactory {
  switch (env.PROVIDER) {
    case 'sendgrid':
      return {
        email: () => new SendGridEmailProvider(env.SENDGRID_KEY),
        sms:   () => new TwilioSmsProvider(env.TWILIO_SID, env.TWILIO_TOKEN),
      };
    case 'resend':
      return {
        email: () => new ResendEmailProvider(env.RESEND_KEY),
        sms:   () => new VonageSmsProvider(env.VONAGE_KEY),
      };
    default:
      return {
        email: () => new StubEmailProvider(),
        sms:   () => new StubSmsProvider(),
      };
  }
}
```

## Worker Entry Point

```typescript
// worker.ts
import { createNotificationFactory } from './factory';

export interface Env {
  PROVIDER:     string;
  SENDGRID_KEY: string;
  RESEND_KEY:   string;
  TWILIO_SID:   string;
  TWILIO_TOKEN: string;
  VONAGE_KEY:   string;
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const factory = createNotificationFactory(env);
    const email   = factory.email();

    const body = await req.json<{ to: string; subject: string; text: string }>();
    const result = await email.send(body);

    return Response.json({ sent: true, id: result.id });
  },
};
```

## Environment-scoped wrangler.toml

```toml
[vars]
PROVIDER = "stub"   # safe default for dev

[env.production.vars]
PROVIDER = "resend"

[env.production.secrets]
# RESEND_KEY set via `wrangler secret put`
```

## Anti-patterns

- **Branching inside handlers** — `if (env.PROVIDER === 'sendgrid') { ... }` scattered
  throughout handler code means every new provider requires hunting down all branches.
  Consolidate all provider knowledge into the factory.
- **Returning raw provider objects** — Returning `SendGridEmailProvider` as the type
  (instead of `EmailProvider`) couples callers to the concrete class and prevents
  swapping at compile time.
- **One factory, one provider** — If your factory only ever creates one type (e.g., just
  email), call it a provider factory and name it accordingly; the Abstract Factory is
  for families of related products.

## Gotchas

- Workers don't support constructor injection via a framework; the factory call happens
  at handler invocation time, not module load time — this is intentional so it picks up
  secrets from `env` which are not available at module scope.
- The `PROVIDER` variable must be set in every environment (`dev`, `staging`,
  `production`) or the switch falls through to the stub silently.
- Keep stub providers in `src/providers/` and not behind a `process.env.NODE_ENV`
  guard — Workers have no `process.env`; use `env.PROVIDER === 'stub'` instead.

## Verification

```typescript
// test/factory.test.ts
import { createNotificationFactory } from '../src/factory';
import { StubEmailProvider } from '../src/providers/email-stub';

const factory = createNotificationFactory({
  PROVIDER: 'stub',
  SENDGRID_KEY: '',
  RESEND_KEY: '',
} as any);

const emailProvider = factory.email();
const { id } = await emailProvider.send({ to: 'test@example.com', subject: 'Hi', text: 'Hello' });
console.assert(id.startsWith('stub-'), 'Stub should return a stub id');
console.assert(emailProvider instanceof StubEmailProvider);
```

Run `wrangler dev` with `PROVIDER=stub` and verify no external calls are made; switch
to `PROVIDER=resend` and confirm the correct API key is used.

## Related

- `strategy-pattern-workers-kv.md` — single-product strategy selection
- `bridge-pattern-workers-storage-backend-abstraction.md` — separating abstraction from
  implementation for storage
- `decorator-pattern-workers-middleware-composition.md` — wrapping providers with
  cross-cutting concerns (logging, retry)

## Sources

- GoF *Design Patterns* (1994) — Abstract Factory, pp. 87–95
- Cloudflare Workers environment bindings: https://developers.cloudflare.com/workers/configuration/environment-variables/
- Wrangler environments: https://developers.cloudflare.com/workers/wrangler/environments/
