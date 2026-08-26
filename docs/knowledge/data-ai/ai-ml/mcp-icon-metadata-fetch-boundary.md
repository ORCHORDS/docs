# MCP icon-metadata fetch boundary

**Issue:** MCP icon metadata can point clients at remote or embedded images. Rendering server-supplied icons creates URL-fetch, media-decoding, tracking, and cache-isolation boundaries unrelated to tool authority.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

Allowlist schemes/media types/sizes; fetch remotely without ambient credentials; block private/link-local destinations; sanitize decoding; partition cache by server identity and cap data URIs.

## Verification

Test redirects, SVG/script payloads, decompression bombs, huge data URIs, private IPs, credential reflection, cache collision, and unsupported clients.

## Gotchas

An icon is untrusted presentation data, not an authenticated brand claim. Specification-version negotiation determines whether metadata is supported.

## Official sources

- https://modelcontextprotocol.io/specification/2025-06-18/basic/index
