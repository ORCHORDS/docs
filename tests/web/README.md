# Web Tests

**Project:** Beetle Studio
**Owner:** Lisa Martinez (QA Lead)
**Version:** 1.0.0
**Last Updated:** June 2026

---

## Overview

Browser-based tests for Beetle Studio's web components: the license activation portal, cloud project dashboard, and documentation site. Uses Playwright for cross-browser testing.

---

## Browser Test Framework

| Component | Technology |
|---|---|
| Framework | Playwright (.NET) |
| Browsers | Chromium, Firefox, WebKit |
| Runner | dotnet test |
| CI Label | ubuntu-latest |

---

## Test Structure

`
tests/web/
├── README.md
├── BeetleStudio.WebTests.csproj
├── playwright.config.ts
├── LicensePortal/
│   ├── ActivationTests.cs
│   └── TrialTests.cs
├── CloudDashboard/
│   ├── LoginTests.cs
│   ├── ProjectListTests.cs
│   └── SyncTests.cs
└── Docs/
    ├── NavigationTests.cs
    └── SearchTests.cs
`

---

## Running Tests

`ash
# Install browsers
npx playwright install

# Run all web tests
dotnet test tests/web/

# Run specific suite
dotnet test --filter "FullyQualifiedName~LicensePortal"

# Run headed (visible browser)
HEADED=1 dotnet test tests/web/
`

---

## Document Maintenance

### Change Log

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0.0 | June 2026 | Lisa Martinez | Initial document |