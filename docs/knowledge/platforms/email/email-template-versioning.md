# email-template-versioning

**Issue:** Managing email template versions to enable rollback and A/B testing
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Templates change frequently; without versioning, bugs in production emails cannot be rolled back and A/B tests cannot be run cleanly.

## Pattern / Solution
1. Store templates in database with version column:
```sql
CREATE TABLE email_templates (
  id SERIAL PRIMARY KEY,
  slug TEXT NOT NULL,
  version INTEGER NOT NULL,
  subject TEXT,
  html_body TEXT,
  text_body TEXT,
  is_active BOOLEAN DEFAULT false,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
```
2. Only one version per slug is active at a time; activate via migration.
3. Render always uses active version: `SELECT * FROM email_templates WHERE slug=$1 AND is_active=true`.
4. For A/B testing: two active versions with traffic split percentage column.
5. Keep at least 90 days of version history for audit and rollback.

## Gotchas
- Compiled templates (MJML -> HTML) should store both source and compiled output.
- Template changes that break personalization variables require data migration.
- Cache compiled templates with version-based cache key; bust on activation.

## Related
- email-a-b-testing, handlebars-email-templates, mjml-template-framework, email-personalization-patterns
