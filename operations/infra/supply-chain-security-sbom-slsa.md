# Supply Chain Security: SBOM and SLSA

## Overview

Supply chain security has become critical in modern software development, requiring comprehensive visibility into dependencies and provenance. Software Bill of Materials (SBOM) and Software Supply Chain Levels for Software Artifacts (SLSA) provide essential frameworks for securing the software supply chain.

## What is an SBOM?

An SBOM (Software Bill of Materials) is a formal inventory of all components, libraries, and dependencies used in building software. It provides transparency into the software supply chain, enabling organizations to identify vulnerabilities, track licensing compliance, and manage security risks effectively.

## SLSA Framework

SLSA (Software Supply Chain Levels for Software Artifacts) is a security framework that defines security requirements for software artifacts throughout their lifecycle. SLSA Level 3 represents a significant security milestone requiring:
- Provenance through OIDC
- Dependency snapshot verification
- Artifact signing with cosign
- Complete build process transparency

## Syft/CycloneDX SBOM Generation

Syft generates SBOMs by scanning container images, filesystems, and packages to create detailed component inventories. CycloneDX format provides standardized SBOM structure for interoperability.

```yaml
# syft config file
output:
  - cyclonedx-json
  - spdx-json
  - table
```

```bash
# Generate SBOM with Syft
syft registry.example.com/my-app:latest -o cyclonedx-json > sbom.json

# Scan filesystem
syft /path/to/app -o cyclonedx-json > sbom.json
```

## Cosign Signing

Cosign provides artifact signing and verification capabilities using public key cryptography. It ensures artifact integrity and authenticity through cryptographic signatures.

```yaml
# cosign configuration
apiVersion: v1
kind: Pod
metadata:
  name: build-pod
spec:
  containers:
  - name: builder
    image: gcr.io/cloud-builders/docker
    command:
    - /bin/sh
    - -c
    - |
      docker build -t $IMAGE_NAME .
      cosign sign $IMAGE_NAME
```

```bash
# Sign container image
cosign sign --key cosign.key $IMAGE_NAME

# Verify signature
cosign verify --key cosign.pub $IMAGE_NAME
```

## SLSA Level 3 Attestation

SLSA Level 3 requires complete build provenance, including:
- OIDC-based identity verification
- Dependency snapshot creation
- Artifact signing and verification
- Complete build process documentation

```yaml
# GitHub Actions workflow for SLSA Level 3
name: SLSA Provenance
on:
  push:
    branches: [ main ]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v4

    - name: Set up Docker Buildx
