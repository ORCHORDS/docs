# GitHub Issue Forms — Structured YAML Form Schemas

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

---

## Symptom / Use-case

Markdown issue templates ask contributors to fill in freeform text sections, but:
- Bug reports arrive without reproduction steps.
- Feature requests omit priority or affected component.
- There is no way to make a field required before the issue can be submitted.
- Labels and assignees must be set manually after triage.

GitHub Issue Forms replace the Markdown template with a validated web form. Fields can be required, typed (text input, text area, dropdown, checkboxes, URL), and the rendered issue body is automatically structured from the answers.

---

## Context

Issue Forms are defined as YAML files stored in `.github/ISSUE_TEMPLATE/`. They use the key `body:` (an array of field objects) instead of the freeform Markdown that the older template format used.

When a contributor clicks "New Issue" on a repo with issue forms, GitHub renders a form UI. The issue body the form generates is structured Markdown (headings + content) — it can be parsed reliably by automation.

**Supported field types:**

| `type` | Purpose |
|---|---|
| `markdown` | Static instructional text (not collected as input) |
| `input` | Single-line text |
| `textarea` | Multi-line text (optionally rendered with `render: shell` syntax highlighting) |
| `dropdown` | Select-one from a list |
| `checkboxes` | Multi-select checkboxes |

**Top-level keys:**

| Key | Required | Purpose |
|---|---|---|
| `name` | yes | Template name shown in the selector |
| `description` | yes | Short description shown in the selector |
| `title` | no | Pre-filled issue title (supports `[PREFIX]` patterns) |
| `labels` | no | Labels auto-applied on submission |
| `assignees` | no | Assignees auto-applied |
| `projects` | no | Project numbers to add the issue to |
| `body` | yes | Array of field objects |

---

## Bug Report Form

```yaml
# .github/ISSUE_TEMPLATE/bug_report.yml
name: Bug Report
description: Report a reproducible bug in the application
title: "[Bug]: "
labels:
  - bug
  - needs-triage
assignees:
  - platform-oncall
body:
  - type: markdown
    attributes:
      value: |
        Thanks for taking the time to fill out this bug report.
        Please search existing issues before submitting to avoid duplicates.

  - type: input
    id: version
    attributes:
      label: Application version
      description: Run `myapp --version` and paste the output.
      placeholder: "1.4.2"
    validations:
      required: true

  - type: dropdown
    id: environment
    attributes:
      label: Environment
      description: Where does the bug occur?
      options:
        - Production
        - Staging
        - Local development
        - CI
    validations:
      required: true

  - type: textarea
    id: reproduction
    attributes:
      label: Steps to reproduce
      description: Provide a minimal, complete, and reproducible example.
      placeholder: |
        1. Start the server with `myapp serve`
        2. Send request: `curl http://localhost:3000/api/users`
        3. Observe error in response
    validations:
      required: true

  - type: textarea
    id: expected
    attributes:
      label: Expected behaviour
      placeholder: A list of users is returned with HTTP 200.
    validations:
      required: true

  - type: textarea
    id: actual
    attributes:
      label: Actual behaviour
      placeholder: HTTP 500 with `Cannot read property 'id' of undefined`.
    validations:
      required: true

  - type: textarea
    id: logs
    attributes:
      label: Relevant log output
      description: Paste any relevant logs. This will be automatically formatted as code.
      render: shell

  - type: checkboxes
    id: checklist
    attributes:
      label: Checklist
      options:
        - label: I have searched existing issues and this is not a duplicate.
          required: true
        - label: I have read the contributing guide.
          required: false
```

---

## Feature Request Form

```yaml
# .github/ISSUE_TEMPLATE/feature_request.yml
name: Feature Request
description: Suggest a new feature or enhancement
title: "[Feature]: "
labels:
  - enhancement
body:
  - type: dropdown
    id: area
    attributes:
      label: Product area
      options:
        - API
        - Dashboard
        - CLI
        - Documentation
        - Infrastructure
        - Other
    validations:
      required: true

  - type: textarea
    id: problem
    attributes:
      label: Problem statement
      description: |
        What problem does this feature solve?
        Use the format: "As a [role], I want [capability] so that [benefit]."
    validations:
      required: true

  - type: textarea
    id: solution
    attributes:
      label: Proposed solution
      description: Describe the solution you'd like. Include API designs or UI mockups if relevant.
    validations:
      required: true

  - type: textarea
    id: alternatives
    attributes:
      label: Alternatives considered
      description: What workarounds or alternative approaches did you evaluate?

  - type: input
    id: priority
    attributes:
      label: Business impact (optional)
      description: How many users or revenue is affected? This helps us prioritise.
      placeholder: "~200 enterprise customers cannot use X without this"
```

---

## Blank Issue Escape Hatch

If you have issue forms but still want to allow blank (freeform) issues — for example for internal team members — add a `config.yml`:

```yaml
# .github/ISSUE_TEMPLATE/config.yml
blank_issues_enabled: true
contact_links:
  - name: Security vulnerability
    url: https://example.com/security
    about: Please report security issues via our private disclosure page, not GitHub Issues.
  - name: Community forum
    url: https://community.example.com
    about: Ask usage questions in the forum before opening an issue.
```

`blank_issues_enabled: false` hides the "Open a blank issue" link entirely, forcing all new issues through a form.

---

## Parsing Issue Form Output in Automation

Because issue forms produce deterministic Markdown, you can parse the body reliably in a GitHub Actions workflow:

```yaml
name: Triage new issues

on:
  issues:
    types: [opened]

jobs:
  triage:
    runs-on: ubuntu-latest
    permissions:
      issues: write

    steps:
      - name: Extract environment field
        id: parse
        env:
          BODY: ${{ github.event.issue.body }}
        run: |
          # Issue forms produce "### Environment\n\nProduction\n"
          ENV=$(echo "$BODY" | awk '/^### Environment/{found=1; next} found && NF{print; exit}')
          echo "environment=$ENV" >> "$GITHUB_OUTPUT"

      - name: Add production label
        if: steps.parse.outputs.environment == 'Production'
        uses: actions/github-script@v7
        with:
          script: |
            github.rest.issues.addLabels({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.issue.number,
              labels: ['production-impact']
            })
```

The section heading in the rendered body matches the `label:` value from the form definition, prefixed with `###`.

---

## Anti-patterns

- **Using `markdown` type fields to collect input.** The `markdown` type is display-only — it is never included in the submitted issue body. Use `input` or `textarea` for any field you need to read back.

- **Setting `required: true` on checkbox groups.** Only individual checkbox `options` support `required: true` (force the contributor to check that box). The top-level `validations.required` on a `checkboxes` block makes the entire group mandatory, meaning at least one must be checked — which is rarely what you want.

- **Overly long dropdown lists.** More than 10–15 options in a dropdown degrades usability. Consider grouping into fewer categories or using an `input` with placeholder guidance.

- **Forgetting to escape YAML special characters in labels.** Option strings containing `:` must be quoted: `"Option: value"`. Unquoted colons inside `options:` arrays cause a YAML parse error and GitHub will fall back to the blank issue template silently.

- **Relying on free-text parsing when a `dropdown` would suffice.** If you intend to parse a field in automation, use `dropdown` or `checkboxes` — they produce stable, known output values. `textarea` fields depend on user discipline.

---

## Gotchas

- **Issue forms do not work in private repos on Free plan.** Issue forms (YAML) require at minimum a GitHub Team plan for private repos. Public repos have no restriction.

- **`assignees:` field requires the assignee to be a collaborator.** GitHub silently ignores assignee values that are not collaborators on the repo — no error is surfaced to the contributor.

- **`labels:` in the form YAML must already exist in the repo.** Labels that do not exist are silently ignored; they are not auto-created. Pre-create labels via the Labels settings page or via a bootstrapping script.

- **The form is rendered only in the web UI.** Contributors opening issues via `gh issue create` or the REST API bypass form validation entirely. Enforce structure for API-created issues with a separate triage workflow that checks `body` for expected headings.

- **Changing field `id` values breaks automation.** The `id:` field on each form element does not appear in the rendered issue body — only the `label:` heading does. But the `id:` is used internally by GitHub for form state. If you rename a `label:` in a form, update any automation that parses by that heading string.

---

## Verification

```bash
# List all issue templates in the repo
ls .github/ISSUE_TEMPLATE/

# Validate YAML syntax locally
python3 -c "import yaml, sys; yaml.safe_load(open(sys.argv[1]))" \
  .github/ISSUE_TEMPLATE/bug_report.yml && echo "YAML OK"

# Check that templates appear in the GitHub UI
gh repo view --web   # Navigate to Issues → New Issue
```

Alternatively, use an online JSON Schema validator against:
`https://raw.githubusercontent.com/nicklockwood/SwiftyJSON/master/github_issue_forms_schema.json`

Or check with `check-jsonschema`:

```bash
pip install check-jsonschema
check-jsonschema --schemafile \
  https://json.schemastore.org/github-issue-forms.json \
  .github/ISSUE_TEMPLATE/bug_report.yml
```

---

## Related

- `issue-and-pr-templates.md` — older Markdown-based issue templates
- `github-labels-automation.md` — automating label creation to match form YAML
- `github-issue-types-org-triage.md` — org-level issue type taxonomy
- `github-sub-issues-tasklists.md` — connecting issues into structured task trees
- `github-projects-v2-2026.md` — routing form submissions into project boards

---

## Sources

- GitHub Docs: "Configuring issue templates for your repository" — https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/configuring-issue-templates-for-your-repository
- GitHub Docs: "Syntax for issue forms" — https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/syntax-for-issue-forms
- GitHub Docs: "About issue and pull request templates" — https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/about-issue-and-pull-request-templates
