# Helm OCI Chart Registry Provenance

**Issue:** Helm v3 transitioned the default distribution channel for charts from HTTP-based repositories to OCI registries, and operators who treat OCI registries as opaque storage lose the provenance, signing, and discovery guarantees that the original index.yaml model provided. Engineering teams need a working understanding of how Helm stores charts as OCI artifacts, how the OCI image-spec overlays map onto chart provenance, and what the practical consequences are for signing, mirroring, and auditability.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The OCI Mapping

A Helm chart in OCI form is an OCI artifact of media type `application/vnd.cncf.helm.chart.content.v1.tar+gzip`, organized into a logical repository whose name is the chart name and whose tags are chart versions. Push and pull operations go through the standard OCI distribution APIs: `oras push`, `helm push`, or registry-native clients. The OCI 1.1 distribution specification defines content-addressable storage, layer deduplication, and tag mutability semantics that govern how registries behave under retries and concurrent writes.

The chart tarball itself is one layer. A separate config layer can carry the `Chart.yaml` metadata so registries can serve a chart listing without extracting the tarball. Helm's own push implementation sets the artifact manifest media type to `application/vnd.cncf.helm.chart.v1` and the config media type to `application/vnd.cncf.helm.config.v1+json`, and clients inspect those media types to recognize the artifact as a Helm chart.

## Provenance And Signing

Helm provenance is a JSON document signed with a PGP key embedded in the chart package; when Helm repackages a chart with `helm package --sign --key ... --keyring ...`, it produces a `.tgz` plus a `.prov` file. Under the classic HTTP registry model, the provenance file lived alongside the chart and clients could fetch both. Under the OCI model, provenance is not an officially supported first-class media type, so operators who need signed charts must rely on registry-side signing rather than the chart-level provenance file.

In practice, this means adopting a signing system like Cosign that signs the OCI artifact reference, or running a registry with notation or sigstore-integrated signing. The verification command becomes `cosign verify --certificate-identity ... registry.example.com/charts/mychart:1.2.3`. Operators must therefore publish charts through a pipeline that signs on push and reject any chart that is not accompanied by a verifiable signature in the registry.

## Mirroring And Cache Poisoning

OCI mirroring uses the same distribution APIs as container image mirroring. Tools like `crane copy` translate chart references like `ghcr.io/org/charts/mychart:1.2.3` to target registries. Because Helm treats OCI registries as content-addressable, mirroring preserves identity when the digest is preserved, but identity is lost when the tag is rewritten. Tags are mutable in most OCI registries, so a mirror that copies by tag can drift from upstream.

A robust mirror pipeline copies by digest and re-applies the tag locally, so the mirror cannot be tricked into serving a chart with the right tag and a different digest than the upstream. Cache poisoning at this layer is rare but high-impact because the chart consumer typically does not check the digest returned by the pull. Force consumers to use the digest form, or wrap pull with a tool that re-tags after verification.

## Index Discovery And Catalog Drift

The classic HTTP Helm repository used `index.yaml` as a discovery surface; OCI registries do not expose such a unified index. Discovery happens through the registry's tag listing endpoint, which is typically restricted to authenticated callers and may be rate-limited. Operators building a chart portal must accept that discovery latency will be higher than the index-based model and that catalog freshness is determined by the registry, not by the chart author.

Catalog drift occurs when a chart is re-pushed with the same tag but different content; in OCI terms the digest changes but the tag does not. Consumers pinning by tag will silently receive the new content. The mitigation is to refuse tag reuse entirely in the publishing pipeline: require that every push use a content-addressable tag, or fail the push if the tag already exists. This aligns chart publishing with container image best practice.

## Failure Modes

The most common operational failure is treating OCI registries like HTTP repositories and skipping digest verification. A second is configuring a chart repository as an OCI URL but storing it in a registry that does not allow nested repository paths, causing 404s on legitimate pushes. A third is signing the chart at packaging time but not signing the OCI artifact, so an attacker can repackage the chart with a new digest and the original signature no longer matches the artifact in the registry. Run `cosign verify` against every pulled chart as a deployment gate, not just at packaging.

Operational incidents also occur when registry garbage collection deletes unreferenced layers. Helm charts reference layers by digest, so unreferenced layer cleanup is safe, but registries that share storage between charts and container images may evict layers aggressively. Configure retention policies that exempt the chart namespace and verify that mirror pipelines can re-fetch upstream layers on demand.

## Canonical sources

1. https://helm.sh/docs/v3/topics/registries/
2. https://github.com/opencontainers/distribution-spec/blob/main/spec.md