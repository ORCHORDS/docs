# feature-cookbook-onboarding

**Issue:** User onboarding — signup, activation, retention
**Date:** 2026-08-09
**Status:** documented

## Symptom
You launch your app. Users sign up. Half of them never
come back. You wish you'd done something to keep them.

## Root cause
**Onboarding is a feature.** Without it, users don't
activate.

**Source:** Various product guides.

## The "signup" pattern

For signup, ask for the minimum:
```ts
// Minimal: email + password
interface SignupInput {
  email: string;
  password: string;
}

// Plus a name (optional, can be added later)
interface SignupInput {
  email: string;
  password: string;
  displayName?: string;
}
```

The fewer fields, the higher the conversion.

## The "social signup" pattern

For social signup:
```tsx
function SignupForm() {
  return (
    <form>
      <button onClick={signupWithGoogle}>
        <GoogleIcon /> Sign up with Google
      </button>
      <button onClick={signupWithApple}>
        <AppleIcon /> Sign up with Apple
      </button>

      <hr />

      <input type="email" name="email" placeholder="Email" />
      <input type="password" name="password" placeholder="Password" />
      <button type="submit">Sign up with email</button>
    </form>
  );
}
```

Social signup is faster; more users complete it.

## The "double opt-in" pattern

For GDPR compliance:
1. User signs up
2. Email is sent with a confirmation link
3. User clicks the link
4. The user is confirmed

```ts
async function signup(input: SignupInput, env: Env): Promise<void> {
  const confirmationToken = crypto.randomUUID();

  await env.DB!.prepare(
    `INSERT INTO users (id, email, status, confirmation_token) VALUES (?, ?, 'pending', ?)`
  ).bind(crypto.randomUUID(), input.email, confirmationToken).run();

  await sendEmail({
    to: input.email,
    subject: 'Confirm your email',
    html: `<a href="https://example.com/confirm?token=<redacted-secret>
  }, env);
}
```

The user is active only after confirmation.

## The "activation" pattern

For activation, take the user to the value:
```tsx
// After signup, take the user to the next step
function PostSignup() {
  return (
    <div>
      <h1>Welcome! Let's get started.</h1>
      <button onClick={goToOnboarding}>Start onboarding</button>
      <button onClick={skipToApp}>Skip for now</button>
    </div>
  );
}
```

The user is taken to the next step.

## The "onboarding" pattern

For onboarding, guide the user:
```ts
const ONBOARDING_STEPS = [
  { id: 'profile', title: 'Set up your profile', component: ProfileStep },
  { id: 'first_action', title: 'Create your first post', component: FirstPostStep },
  { id: 'invite', title: 'Invite friends', component: InviteStep },
  { id: 'verify', title: 'Verify your email', component: VerifyStep },
];
```

The steps are sequential; each has a clear value.

## The "progress" pattern

For onboarding, show progress:
```tsx
<ProgressBar currentStep={currentStep} totalSteps={ONBOARDING_STEPS.length} />
```

The user knows how much is left.

## The "skip" pattern

For onboarding, allow skip:
```tsx
<button onClick={skipStep}>Skip this step</button>
```

The user can skip; the app still works.

## The "save state" pattern

For onboarding, save state:
```sql
CREATE TABLE onboarding_progress (
  user_id TEXT PRIMARY KEY,
  step_id TEXT NOT NULL,
  completed_at TEXT,
  skipped_at TEXT
);
```

The user can resume; the step isn't lost.

## The "activation metric" pattern

For activation, define the key metric:
```ts
async function trackActivation(userId: string, action: string, env: Env): Promise<void> {
  await env.ANALYTICS.writeDataPoint({
    blobs: ['activation', action, userId],
    doubles: [1],
    indexes: ['activation'],
  });
}

// Track: did the user do the "magic moment"?
const MAGIC_MOMENT = 'first_post_created';

if (action === MAGIC_MOMENT) {
  await trackActivation(userId, action, env);
}
```

The activation metric is the key indicator.

## The "retention" pattern

For retention, send reminders:
```ts
// Daily / weekly digest
async function sendDailyDigest(userId: string, env: Env): Promise<void> {
  const user = await getUser(userId, env);
  const activity = await getActivity(userId, env);

  await sendEmail({
    to: user.email,
    subject: `You have ${activity.notifications} new updates`,
    html: renderDigest(activity),
  }, env);
}
```

The user is reminded to come back.

## The "win-back" pattern

For inactive users, send a win-back:
```ts
async function sendWinBackEmail(userId: string, env: Env): Promise<void> {
  const user = await getUser(userId, env);
  const daysSinceLastActive = (Date.now() - user.lastActiveAt) / (24 * 60 * 60 * 1000);

  if (daysSinceLastActive > 30 && daysSinceLastActive < 60) {
    // 30-60 days inactive
    await sendEmail({
      to: user.email,
      subject: 'We miss you!',
      html: '<p>Come back and see what\'s new.</p>',
    }, env);
  }
}
```

The user is reminded; the app brings them back.

## The "first-run experience" pattern

For first run, show a tour:
```tsx
function FirstRun() {
  return (
    <Tour
      steps={[
        { selector: '.header', title: 'Navigation', content: 'Use this to navigate the app' },
        { selector: '.main', title: 'Your content', content: 'This is where your content lives' },
        { selector: '.settings', title: 'Settings', content: 'Customize the app here' },
      ]}
    />
  );
}
```

The user is guided through the app.

## The "personalized welcome" pattern

For personalized welcome, use the user's data:
```ts
const greeting = user.displayName
  ? `Welcome back, ${user.displayName}!`
  : 'Welcome back!';
```

A personalized welcome is warmer.

## The "tutorial" pattern

For complex features, a tutorial:
```tsx
function Tutorial({ onComplete }: { onComplete: () => void }) {
  return (
    <Modal>
      <h1>How to use the dashboard</h1>
      <p>The dashboard shows your data. Click here to filter.</p>
      <button onClick={onComplete}>Got it</button>
    </Modal>
  );
}
```

The user is shown how to use the feature.

## The "user feedback" pattern

For feedback, ask:
```tsx
function PostActionFeedback() {
  return (
    <div>
      <p>How was that?</p>
      <button>👍 Good</button>
      <button>👎 Bad</button>
    </div>
  );
}
```

The user provides feedback; the team improves.

## Verification
- **Test:** Signup flow works
- **Test:** Onboarding saves state
- **Test:** Activation is tracked
- **Live:** Conversion is monitored
- **Audit:** Quarterly review of onboarding

## Gotchas
- **The "too many fields" anti-pattern.** Users abandon
  forms with many fields.
- **The "no skip" anti-pattern.** Users drop off; allow
  skip.
- **The "no progress" anti-pattern.** A 5-step onboarding
  with no progress looks long.
- **The "no activation metric" anti-pattern.** You don't
  know if onboarding is working.
- **The "no win-back" anti-pattern.** Users who leave
  are gone; bring them back.

## Related
- `feature-cookbook-auth.md`
- `feature-cookbook-comms.md`
- `feature-cookbook-analytics.md`
- `feature-observability-pattern.md`
- `feature-cookbook-email.md`
- `gdpr-article-17-erasure.md`
- `audit-log-as-product.md`
