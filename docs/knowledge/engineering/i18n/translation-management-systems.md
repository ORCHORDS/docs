# Translation Management Systems

## Overview

Translation Management Systems (TMS) streamline localization workflows by centralizing translation processes, managing glossaries, and integrating with development tools. Popular platforms include Crowdin, Lokalise, and Transifex, each offering unique features for different team sizes and requirements.

## Platform Comparison

### Crowdin
Crowdin excels in collaborative translation with robust community features. It offers extensive CI/CD integration through webhooks and APIs. Pricing starts at $12/month for basic teams.

### Lokalise
Lokalise focuses on developer-friendly workflows with powerful API integrations. It provides advanced workflow automation and supports multiple file formats. Pricing begins at $15/user/month.

### Transifex
Transifex offers enterprise-grade features with strong AI-powered translation assistance. It integrates well with major development platforms like GitHub and Jira. Pricing starts at $20/user/month.

## Workflow Features

All three platforms support standard workflows including:
- File upload and synchronization
- Translation memory integration
- Glossary management
- Quality assurance checks
- Version control

### Example workflow setup in Crowdin:
```yaml
# crowdin.yml
project_id: 12345
api_token: "your_api_token"
base_path: "."
files:
  - source: /src/en/*.json
    translation: /src/%locale%/%file%.json
```

## Reviewer Roles and Permissions

### Crowdin Role Structure:
```json
{
  "admin": {
    "permissions": ["manage_project", "edit_translations"],
    "access": "full"
  },
  "translator": {
    "permissions": ["translate", "review"],
    "access": "limited"
  }
}
```

### Lokalise Access Control:
```yaml
# .lokasafe.yml
roles:
  - name: "Senior Translator"
    permissions:
      - translate
      - review
      - manage_glossary
```

## CI Integration

### GitHub Actions Integration:
```yaml
name: Translate
on: [push]
jobs:
  translate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Upload to Transifex
        uses: transifex/cli-action@v1
        with:
          token: ${{ secrets.TRANSIFEX_TOKEN }}
```

### Crowdin Webhook Example:
