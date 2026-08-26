# config-bake-vs-render-deploy-time

**Issue:** Every deploy pipeline has to answer one structural question: does configuration get baked into the artifact at build time, or rendered and injected at deploy time? Bake the wrong things and you rebuild (and re-test, and re-verify) a different artifact per environment — losing the build-once-promote-everywhere guarantee and opening a gap between what was tested and what runs. Render the wrong things and your "immutable artifact" is really a template whose behavior depends on what a deploy-time process splices into it, so configuration drift and rendering-tool bugs move into the production path. Teams rarely make this choice explicitly; it accretes from Dockerfile habits and Helm examples, then bites during an incident when nobody knows which config actually produced the running process.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The two models

1. **Baking (build-time configuration).** The artifact is produced fully configured: a Packer image with the app and its settings installed, or a container image built per environment with values written in. Baked artifacts are maximally deterministic — what you scan and test is byte-for-byte what runs — but every configuration change is a rebuild, and an environment-specific image is not promotable.
2. **Rendering (deploy-time configuration).** One environment-neutral artifact is built once; configuration is applied when it deploys — environment variables (the twelve-factor doctrine from 12factor.net/config), Kubernetes ConfigMaps and Secrets, or Helm/Kustomize overlays rendered into manifests at apply time. Config changes deploy without rebuilds, and the same digest moves dev to staging to prod.
3. **Frying (runtime configuration).** A third mode where the instance fetches or mutates its own configuration after boot (config service, startup scripts mutating files). It maximizes flexibility and minimizes auditability; useful for large fleets and fast-changing values, dangerous as a default because running state can drift from any reviewed artifact.

## What current best practice says to bake

1. **Bake code and code-shaped dependencies.** Compiled binaries, vendored libraries, static assets, and base OS layers belong in the immutable artifact. These change at code-review speed and deserve the full build-test-scan-sign pipeline; rebuilding them per environment buys nothing (see container-image-tagging.md and docker-layer-caching-ci.md).
2. **Bake deployment-shaped structure, not values.** The shape of configuration — which keys exist, their schema, their validation — travels with the code so the artifact can refuse to start with invalid config (fail fast at boot with a schema check, not at first use in production).
3. **Bake nothing secret, ever.** Secrets in images are permanent residents of every registry, cache, and scanner they pass through; they cannot be rotated without a rebuild and they leak through layer history. Secrets render at deploy time from a secret store — this is non-negotiable across current guidance (see gitops-secrets-management.md and ansible-vault-secrets.md).

## What current best practice says to render

1. **Render environment identification.** Endpoints, resource limits, log verbosity, feature-flag defaults: anything that legitimately differs between dev, staging, and prod should enter at deploy time so one artifact digest is provably the same artifact that passed staging (the core of the Akuity/Kargo promotion model: promote the same artifact through stages, apply environment config per stage).
2. **Render secrets and short-lived credentials.** Secret values, OIDC-federated deploy credentials, and expiring tokens are bound at deployment, not embedded (see oidc-federated-deploy-credentials.md). This keeps rotation a config operation, not a rebuild.
3. **Render knob-shaped values.** Anything an operator may want to tune during an incident — timeouts, pool sizes, sampling rates — should be deploy-time config. A knob baked into the image is a knob with a CI queue in front of it exactly when you can least afford one.

## The hybrid that modern GitOps settled on

1. **Build once, render in CI, apply in CD.** The 2025-2026 consensus pattern (rendered-manifest workflows championed by Christian Hernandez, Google's OCI-artifact GitOps flow, Kargo's promotion patterns): keep the container image environment-neutral, render environment-specific manifests in CI, and store the rendered output as a versioned, immutable artifact (an OCI artifact or a rendered-manifest branch). The GitOps controller then applies plain YAML — no Helm templating surprises in the cluster, and every deployed byte is reviewable as a diff before it merges.
2. **This gives you baked auditability with rendered flexibility.** The rendered manifest is a snapshot: diff it between environments, diff it between versions, blame it. Pure deploy-time rendering inside the cluster hides what the template engine produced; pure baking makes environment comparison impossible because artifacts diverge.
3. **Keep the renderer out of the hot path.** Whether rendering happens in CI or in-cluster, pin the templating tool version and test the render. A Helm upgrade that changes defaulting logic is a deploy tool regression that behaves exactly like an app regression (see risk-based-deployment-gating.md for gating toolchain changes).

## Deciding per configuration key

1. **Ask: does changing this justify a code review?** If yes, bake it with the code. If no — if it is an operational fact about where this artifact is landing — render it. Version number: baked. Region name: rendered.
2. **Ask: would two environments disagree?** Any key where the answer is yes belongs in the rendered overlay, or you will fork images and lose promotion.
3. **Ask: is it a secret or does it expire?** Render at deploy time from a secret store, full stop.
4. **Ask: how would I audit this during an incident?** If the answer requires logging into a machine to inspect a mutated file, the key was fried when it should have been rendered into something diffable — move it left into the deploy pipeline (see env-binding-precedence.md for how binding sources compose).

## Failure modes to watch for

1. **Rebuild-per-environment regression.** The moment a pipeline builds prod images separately from staging images, the "tested in staging" claim is unverifiable — different digests may differ. Make the same-digest promotion an explicit pipeline assertion, not a convention.
2. **Config drift between render source and cluster.** If someone edits a ConfigMap live, the rendered artifact no longer describes reality; drift detection (infrastructure-drift-detection-signals.md, terraform-drift-detection.md) must cover rendered config, not just infrastructure.
3. **Late validation.** Rendering at deploy time moves misconfiguration later in the pipeline unless you validate rendered output — schema-check manifests and run config validation as a deploy gate (pre-production-checklist.md), so a missing key fails the pipeline, not the pod.
