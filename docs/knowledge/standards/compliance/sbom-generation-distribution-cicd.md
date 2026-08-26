# sbom-generation-distribution-cicd

Generating, storing, and distributing a Software Bill of Materials (SBOM) as
part of your CI/CD pipeline. This is the operational counterpart to the EU
Cyber Resilience Act's legal SBOM mandate: the CRA makes SBOMs a **legal
requirement** for products with digital elements sold in the EU (reporting
obligations from Sept 2026, full enforcement Dec 2027), and US Executive
Order 14028 + NIST SP 800-218 (SSDF) require them for federal suppliers.

This article is about *how a developer team actually produces and ships
SBOMs* — the `eu-cyber-resilience-act-*` articles cover the regulation
itself.

## Symptom

- A customer (especially EU government or enterprise) asks for your SBOM as
  a procurement condition and you don't have one.
- An auditor flags "no SBOM generation step in build pipeline" as a SOC 2 /
  CRA / NIS2 gap.
- A CVE drops in a transitive dependency (think Log4Shell, xz-utils) and
  you can't quickly answer "which of our products are affected, and which
  customers have the vulnerable version?"
- Your SBOM is a one-off hand-written spreadsheet that goes stale the day
  after you write it.
- Two of your microservices produce SBOMs in different formats (one SPDX,
  one CycloneDX) and the security team can't ingest either consistently.

## Root cause

SBOMs only have value if they are:
1. **Generated automatically** from the build, not hand-maintained.
2. **Produced for every release artifact**, with version traceability.
3. **In a machine-readable standard format** (CycloneDX or SPDX).
4. **Stored and queryable** so you can do retroactive impact analysis.
5. **Distributed** to customers and to vulnerability databases (per CRA
   Article 14 reporting obligations).

Most teams fail at step 1 (no CI step) or step 4 (the SBOM is generated but
discarded after the build log scrolls).

## Gotchas

- **SBOM generation tools differ by ecosystem and miss transitive deps.**
  `npm sbom` (Node 18+) only emits direct + transitive for npm, not for
  your vendored Go binaries or Docker base image. You need a layered
  approach: language-level tooling + container scanning + OS-package
  listing.
- **Docker base images count.** Your app SBOM must include the OS packages
  from `debian:bookworm-slim` underneath your app. Use `syft` or
  `trivy fs --format cyclonedx` against the image, not just the source.
- **Build-of-record matters.** An SBOM generated from `package-lock.json`
  on a dev laptop is not authoritative — it may differ from what the CI
  built because of `optionalDependencies`, platform-specific resolution,
  or post-install patches. Generate from the CI container *after*
  install, against the actual `node_modules` / `vendor` tree.
- **SBOM must include the artifact version hash.** A CycloneDX BOM without
  a `serialNumber` and the built-image digest is untraceable. Include
  both the component versions AND the digest of the final artifact (Docker
  image SHA, APK signature, binary SHA-256).
- **License fields are required, not optional.** CRA and many customers
  use the SBOM for license compliance too. If your SBOM tool omits
  license info (many do by default), enable it explicitly.
- **VEX (Vulnerability Exploitability eXchange) is the missing half.** An
  SBOM tells you what's *in* the product; a VEX tells you whether a known
  CVE is actually *exploitable* in your config. Pair them: ship a VEX
  document alongside the SBOM so customers aren't forced to patch every
  theoretical CVE.
- **License of the SBOM tool may matter.** Some commercial SBOM generators
  add telemetry or require a paid license to export to CycloneDX. Verify
  your toolchain before automating at scale.

## Fix / practical setup

A minimal, tool-agnostic SBOM pipeline:

1. **Pick one primary format.** CycloneDX (OWASP) is generally the better
   fit for modern app dev (JSON-native, VEX-aware, good CycloneDX-CLI).
   SPDX is the US federal preference. Many teams generate CycloneDX and
   convert to SPDX with `cyclonedx-cli convert`.

2. **Add a generate step to your CI for every artifact type:**

   ```yaml
   # GitHub Actions example — app + container
   - name: Generate app SBOM (Node)
     run: npx @cyclonedx/cyclonedx-npm --output-format JSON \
         --output-file sbom-app.json
   - name: Generate image SBOM
     run: syft myorg/app:${{ github.sha }} -o cyclonedx-json=sbom-image.json
   - name: Merge
     run: cyclonedx merge --input-files sbom-app.json sbom-image.json \
         --output-file sbom-final.json
   ```

3. **Attach the SBOM to the release artifact.** Options:
   - GitHub Releases: upload `sbom-${version}.json` as a release asset.
   - Container registry: push as an OCI artifact ref using
     `oras push <registry>/app:${tag}-sbom`.
   - Signed attachment: `cosign attach sbom --sbom sbom-final.json
     <image-ref>` then `cosign sign` the attestation.

4. **Store centrally and make queryable.** Feed SBOMs into Dependency-Track
   (open source) or a commercial platform (Anchore, Snyk, FOSSA) so the
   security team can run "show me every product using log4j-core 2.14.x"
   against historical SBOMs.

5. **Emit a VEX statement for known non-exploitable CVEs.** Example: your
   app bundles `openssl` with CVE-2024-XXXX but you don't call the
   vulnerable code path. A VEX `not_affected` statement stops customers
   from having to treat it as exploitable.

6. **Automate distribution to customers and to ENISA / the CRA CSIRT** when
   a vulnerability is confirmed (CRA Article 14 requires reporting to
   ENISA within 24h of a known exploitable vulnerability). The SBOM +
   VEX pipeline makes the 24h report possible.

7. **Version and retain SBOMs for the support lifetime + 10 years**
   (CRA requirement). Don't let your SBOM store auto-delete after 90 days.

## References

- EU Cyber Resilience Act, Articles 13 and 14 (SBOM and vulnerability
  reporting obligations).
- OWASP CycloneDX specification (latest: v1.6, includes VEX).
- SPDX 2.3 / 3.0 specification (ISO/IEC 5962:2021).
- NTIA "Minimum Elements for an SBOM" baseline.
- US Executive Order 14028 and NIST SP 800-218 (Secure Software
  Development Framework).
