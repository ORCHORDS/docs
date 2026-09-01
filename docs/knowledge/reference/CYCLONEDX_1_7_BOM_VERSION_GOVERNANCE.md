# CycloneDX 1.7 BOM Version Governance

## Purpose

CycloneDX is an OWASP supply-chain transparency standard for representing bills of materials and related information. The current stable specification is **CycloneDX 1.7**, released October 21, 2025 and published as ECMA-424, 2nd Edition.

CycloneDX 2.0 is described by the project as a future Transparency Exchange Language release and should not be presented as the current stable BOM specification until it is formally released.

## Versioned exchange

CycloneDX defines registered media types for JSON and XML and a Protobuf media type. A specific CycloneDX version can be expressed as a media-type version parameter, and documents conventionally use filenames such as `bom.json`, `bom.xml`, `*.cdx.json`, or `*.cdx.xml`.

Producers and consumers should agree on the exact schema version rather than assuming that every CycloneDX implementation supports the newest release.

## Governance pattern

1. Record the exact CycloneDX specification version used to generate each BOM.
2. Validate output against the corresponding JSON, XML, or Protobuf schema/reference.
3. Confirm downstream tooling supports CycloneDX 1.7 before making 1.7 a required interchange format.
4. Preserve component identifiers, dependency relationships, hashes, and BOM metadata needed to associate the BOM with the artifact or system it describes.
5. Treat conversion from an earlier CycloneDX version as a schema/model migration and validate the result rather than only changing a version field.
6. Record which BOM capabilities are actually populated; schema validity does not imply complete vulnerability, cryptographic, AI, license, or build data.
7. Reject unsupported future versions explicitly rather than interpreting them using an older schema.

## Scope of CycloneDX 1.7

CycloneDX 1.7 can represent software, hardware, services, cryptographic assets, AI models, dependency graphs, vulnerability information, licenses, build formulation, and other transparency data.

That breadth is optional: a particular BOM may contain only a subset. Consumers should inspect the actual document content and not infer that every CycloneDX 1.7 capability is present.

## Media and file handling

Use registered media types when transporting CycloneDX over HTTP where practical. Consumers should validate the declared media type, parse against the expected version, and apply size/resource limits before processing untrusted BOM input.

## Failure modes

- Calling a BOM simply “CycloneDX” without its schema version can hide compatibility problems.
- Assuming all tools that support 1.6 also support 1.7 can break ingestion pipelines.
- Treating the future 2.0 work as the stable BOM standard creates version-status errors.
- Schema-valid output can still be incomplete or contain inaccurate component data.
- Rewriting the version field without transforming changed structures does not create a valid migration.

## Sources

- CycloneDX — Specification Overview: https://cyclonedx.org/specification/overview/
- CycloneDX — v1.7 specification reference: https://cyclonedx.org/docs/1.7/
- CycloneDX specification repository: https://github.com/CycloneDX/specification

## Scope note

This article describes CycloneDX 1.7 version and exchange governance. It does not claim that a particular BOM is complete, accurate, or compliant with any regulatory requirement.