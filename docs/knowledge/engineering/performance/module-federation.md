# module-federation

**Issue:** Multiple micro-frontends duplicate shared dependencies
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Webpack Module Federation allows runtime sharing of modules across separately deployed applications. Without it, each micro-frontend bundles its own React/ReactDOM, causing duplicate code.

## Pattern / Solution
1. Configure ModuleFederationPlugin in each app's webpack config with shared dependencies.\n2. Set singleton: true for React to prevent version conflicts.\n3. Use requiredVersion to enforce compatible semver ranges.\n4. Eager-load shared modules in the shell app to avoid waterfalls.\n5. Version exposed modules independently using semantic versioning.

## Gotchas
- Async boundaries are required around federated modules; wrap with React.lazy + Suspense.\n- Different webpack versions between host and remote cause runtime errors.\n- Cold start for remote containers adds latency; preconnect to remote origins.

## Related
code-splitting-strategies, dynamic-import-patterns, javascript-bundle-size
