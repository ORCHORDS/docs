# react-email-components

**Issue:** Building email templates with React components using react-email
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
TypeScript developers want to use component-based development and type safety for email templates.

## Pattern / Solution
1. Install: `npm install @react-email/components react react-dom`
2. Create template:
```tsx
import { Html, Body, Container, Text, Button } from '@react-email/components';
export default function WelcomeEmail({ name }: { name: string }) {
  return (
    <Html><Body><Container>
      <Text>Hello, {name}!</Text>
      <Button href="https://app.example.com">Get Started</Button>
    </Container></Body></Html>
  );
}
```
3. Render to HTML: `import { render } from '@react-email/render'; const html = render(<WelcomeEmail name="Alice" />);`
4. Preview with dev server: `npx email dev`
5. Integrates directly with Resend, Nodemailer, SES.

## Gotchas
- React Email renders static HTML; no React state or effects at runtime.
- Tailwind CSS support via `@react-email/tailwind` wrapper, but only email-safe properties render.
- Hot reload preview requires email dev server; not the same as a browser dev server.
- Inline styles are used internally; `className` is converted to inline styles by components.

## Related
- resend-setup, mjml-template-framework, email-template-versioning, handlebars-email-templates
