# React Email Template System

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Teams using string-interpolated HTML or MJML report that
debugging is hard, component reuse is impossible, and type
errors surface only at render time. Designers and engineers
maintain separate source files that drift apart over sprints.

## Context

React Email (`@react-email/components`) treats each email as a
React component tree that renders to static HTML at send time.
Components encapsulate styles as inline objects, keeping the
output compatible with every major mail client. The package
ships a local preview server so you can iterate without
sending a real message to an inbox.

## JSX Email Components

The core primitives mirror HTML email conventions:

```tsx
import {
  Html, Head, Body, Container,
  Section, Text, Button,
} from '@react-email/components';

type WelcomeProps = { name: string; ctaUrl: string };

export default function WelcomeEmail({
  name, ctaUrl,
}: WelcomeProps) {
  return (
    <Html lang="en" dir="ltr">
      <Head />
      <Body style={{ backgroundColor: '#f6f9fc' }}>
        <Container style={{ maxWidth: '600px' }}>
          <Section>
            <Text style={{ fontSize: '16px' }}>
              Hi {name},
            </Text>
            <Button
              href={ctaUrl}
              style={{ backgroundColor: '#0070f3' }}>
              Get started
            </Button>
          </Section>
        </Container>
      </Body>
    </Html>
  );
}
```

`<Button>` renders as an MSO VML button + `<a>` tag pair,
not an HTML `<button>`. Never use a native `<button>` element
inside email markup.

## Preview Server

Start the development preview server:

```sh
npx email dev --dir ./emails --port 3001
```

Each `.tsx` file under `./emails` becomes a route. Supply
default props via a named export:

```tsx
export const PreviewProps: WelcomeProps = {
  name: 'Alice',
  ctaUrl: 'https://app.example.com/onboarding',
};
```

The server hot-reloads on save. HTML and plain-text output
tabs are available inline. No real email is sent.

## Tailwind in Emails

Wrap the root element with `<Tailwind>`:

```tsx
import { Tailwind } from '@react-email/tailwind';

export default function NewsletterEmail() {
  return (
    <Tailwind config={{ theme: {
      extend: { colors: { brand: '#0070f3' } },
    }}}>
      <Html>
        <Body className="bg-gray-100 font-sans">
          <Container className="max-w-xl mx-auto">
            <Text className="text-base text-gray-800">
              Hello world
            </Text>
          </Container>
        </Body>
      </Html>
    </Tailwind>
  );
}
```

`@react-email/tailwind` converts class names to inline styles.
Only email-safe CSS is emitted. Flexbox maps to `display:flex`
which Outlook ignores; pair with `<Row>`/`<Column>` table
fallbacks for structural layout.

## Multi-Provider Rendering

`render()` returns a plain HTML string any provider accepts:

```ts
import { render } from '@react-email/render';
import WelcomeEmail from './emails/welcome';

const html = render(
  <WelcomeEmail name="Alice"
    ctaUrl="https://app.example.com" />
);
const text = render(
  <WelcomeEmail name="Alice"
    ctaUrl="https://app.example.com" />,
  { plainText: true }
);

// Resend
await resend.emails.send({
  from: 'noreply@example.com',
  to: 'alice@example.com',
  subject: 'Welcome', html, text,
});
// SendGrid: sgMail.send({ from, to, subject, html, text })
// Postmark: client.sendEmail({ From, To, Subject,
//   HtmlBody: html, TextBody: text })
```

`render()` is synchronous and CPU-bound. Cache the resulting
HTML string rather than re-rendering per send.

## Anti-patterns

- Importing browser globals (`window`, `document`, `location`)
  — they do not exist at server-side render time.
- Using React hooks (`useState`, `useEffect`) — emails are
  fully static; hooks are inert and will not run.
- Relying on CSS class selectors alone — Gmail strips `<style>`
  blocks in many contexts; all styling must survive inlining.
- Nesting `<Text>` inside `<Button>` — produces `<p>` inside
  `<a>`, which clients handle unpredictably.
- Using relative image URLs — `<Img>` requires absolute HTTPS.

## Gotchas

- `<Head>` is required for MSO conditional comments; omitting
  it breaks Outlook layout.
- Gmail clips emails over ~102 KB of rendered HTML. Users see
  a "View entire message" link; tracking pixels in the footer
  are never loaded for clipped messages.
- Tailwind `dark:` variants emit
  `@media (prefers-color-scheme: dark)` which Gmail ignores.
- `npx email build` exports production HTML to `./out/`. Run
  this in CI to catch size regressions early.

## Verification

```sh
# Render to file; check size (Gmail limit: 102 KB)
npx ts-node -e "
const { render } = require('@react-email/render');
const Email = require('./emails/welcome').default;
require('fs').writeFileSync('/tmp/out.html',
  render(Email({ name: 'Test', ctaUrl: 'https://x.com' })));
"
wc -c /tmp/out.html
# Run through Litmus or Email on Acid for client checks
```

## Related

- email/mjml-template-framework.md
- email/handlebars-email-templates.md
- email/email-template-versioning.md
- email/email-html-css-rendering-matrix.md
- email/resend-setup.md

## Source URLs (verified 2026-08-17)

- https://react.email/docs/introduction
- https://react.email/docs/components/tailwind
- https://react.email/docs/utilities/render
- https://caniemail.com/
- https://github.com/resend/react-email
