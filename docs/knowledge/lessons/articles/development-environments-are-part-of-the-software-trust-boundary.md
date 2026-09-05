# Development Environments Are Part of the Software Trust Boundary

**Issue:** Security review focuses on application source and production systems while development, build, test, and distribution environments are treated as ordinary internal tooling.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

NIST SSDF v1.1 added PO.5, **Implement and Maintain Secure Environments for Software Development**. Software can be compromised before release if the environments and tools that create, test, package, or distribute it are compromised, so those environments belong inside the software security trust model.

## Engineering rule

- Inventory development, build, test, and distribution environments that can materially influence released software.
- Apply risk-based access control, hardening, monitoring, patching, credential protection, and change traceability to those environments.
- Include development endpoints, build infrastructure, and privileged automation in threat modeling and incident-response scope.
- Treat environment exceptions as owned security decisions with review dates.
- Verify the release process does not assume internal development infrastructure is inherently trusted.

## Verification

- Trace a release from source change through build/test/distribution and identify every environment with authority to alter the result.
- Confirm representative high-authority environment access is restricted and monitored.
- Verify a configuration or access change in the development infrastructure is attributable to an approved identity/process.

## Official sources

- NIST SP 800-218, Secure Software Development Framework (SSDF) Version 1.1: https://csrc.nist.gov/pubs/sp/800/218/final
- NIST SSDF project page: https://csrc.nist.gov/projects/ssdf
