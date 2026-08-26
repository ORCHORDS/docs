# Workers version override smoke-test boundary

**Issue:** `Cloudflare-Workers-Version-Overrides` can route a request to a specific Worker version in the current deployment, including one at 0% traffic. If an override is malformed or names an ineligible version, Cloudflare silently uses the deployment percentages, so a passing smoke test may have exercised the old version.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Keep the target version in the current deployment and obtain its exact version ID from the deployment record.
- Construct `Cloudflare-Workers-Version-Overrides` as a valid Dictionary Structured Header: Worker name as the key and version ID as a string value.
- Protect production smoke-test ingress with authentication, a narrow source policy, and rate limits. Strip untrusted client-supplied override headers unless the route intentionally authorizes them.
- Read the version metadata binding or trusted observability record and fail the test unless the executed version equals the requested version.
- Keep ordinary traffic at the reviewed deployment percentages; use 0% only as a deliberate temporary test state.
- Expire test credentials and remove the override path from routine client traffic after promotion.

## Implementation and tests

Create a deployment containing the stable version and candidate version, with the candidate at 0%. Send a uniquely tagged smoke request with the override header, then assert response behavior and executed version ID. Exercise an invalid dictionary, unknown Worker key, version outside the current deployment, recently changed deployment, and unauthorized external header.

For downstream service bindings, test header propagation through `fetch()`. Record that RPC-style service-binding calls cannot attach this override header.

## Gotchas and applicability

Workers currently supports two versions in one deployment. A new deployment can take a few seconds to become globally available. Failure to apply an override is a fallback, not an error response, which makes version verification mandatory. An override tests production bindings and data, so use synthetic accounts and reversible operations.

This feature applies to versions in the current deployment; it is not arbitrary historical-version routing.

## Official sources

- [Cloudflare Workers: Version overrides](https://developers.cloudflare.com/workers/versions-and-deployments/version-overrides/)
- [Cloudflare Workers: Version metadata binding](https://developers.cloudflare.com/workers/runtime-apis/bindings/version-metadata/)
