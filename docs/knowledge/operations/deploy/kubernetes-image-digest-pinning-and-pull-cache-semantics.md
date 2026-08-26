# Kubernetes image digest pinning and pull-cache semantics

**Issue:** Mutable image tags can deploy different code to different Pods, while forcing pulls without understanding layer caching can add registry dependency without improving identity guarantees.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

Pin production container images by digest when the deployment must identify immutable bytes. A tag can be moved at the registry; a digest identifies a specific image version. Record human-readable release metadata separately when needed.

With `imagePullPolicy: Always`, the container runtime resolves the image name to a digest each time but can reuse locally cached layers for that digest. This still requires reliable registry resolution. With an explicitly pinned digest, `IfNotPresent` can preserve byte identity while benefiting from local cache, subject to the organization's admission and freshness policy.

## Operational controls

- Resolve and review digests during the trusted build or promotion process.
- Verify signatures or attestations according to supply-chain policy; digest pinning alone does not establish producer trust.
- Set `imagePullPolicy` explicitly because Kubernetes sets its default when the object is first created and does not later revise it merely because the image reference changes.
- Monitor registry availability, pull latency, and `ImagePullBackOff`.
- Ensure multi-architecture references resolve to the intended platform manifests.
- Retain previous digests for tested rollback.

## Verification

1. Deploy the same digest across multiple nodes and confirm identical image IDs.
2. Move a test tag and show that digest-pinned workloads remain unchanged.
3. Restart Pods with cached layers and measure registry resolution and download behavior.
4. Deny registry access and verify expected behavior for each pull policy.
5. Validate the digest through the admission and provenance controls used in production.

## Sources

- [Kubernetes: Images](https://kubernetes.io/docs/concepts/containers/images/)
- [Kubernetes: Image policy webhook](https://kubernetes.io/docs/reference/access-authn-authz/admission-controllers/#imagepolicywebhook)
