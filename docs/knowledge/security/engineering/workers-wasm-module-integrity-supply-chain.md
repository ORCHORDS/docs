# WebAssembly Module Integrity in Cloudflare Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
A Cloudflare Worker loads a WebAssembly module from R2 or a third-party CDN at runtime, and a supply chain compromise or a misconfigured bucket ACL allows a tampered `.wasm` binary to execute inside the Worker's security boundary.

## Context
WebAssembly modules in Cloudflare Workers execute with the same runtime privileges as the surrounding JavaScript: they can read secrets from the `env` object if the Worker passes them as imports, make outbound `fetch` calls via an imported host function, and read/write shared memory. A tampered `.wasm` binary is therefore a complete Worker compromise. The mitigation is to verify a SHA-256 digest of every `.wasm` byte stream before instantiation, comparing it against an expected hash stored in a Worker secret — a value that attackers cannot read or modify without access to the Cloudflare dashboard or Wrangler credentials.

## Bundling WASM at Build Time (Preferred Path)
The safest approach is to bundle the `.wasm` file directly into the Worker bundle via Wrangler's `wasm_modules` binding. The module bytes are verified as part of the Wrangler deploy and uploaded to Cloudflare's infrastructure, making runtime fetching unnecessary.

```toml
# wrangler.toml
[wasm_modules]
IMAGE_PROCESSOR = "src/image_processor.wasm"
CRYPTO_UTILS = "src/crypto_utils.wasm"
```

```typescript
// src/index.ts — bundled WASM, no runtime fetch needed
export interface Env {
  IMAGE_PROCESSOR: WebAssembly.Module;
  CRYPTO_UTILS: WebAssembly.Module;
  // Expected digests for defence-in-depth verification
  IMAGE_PROCESSOR_SHA256: string;
  CRYPTO_UTILS_SHA256: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Instantiate from the pre-bundled module — no network round-trip
    const instance = await WebAssembly.instantiate(env.IMAGE_PROCESSOR, {
      env: buildImports(env),
    });
    return handleWithWasm(request, instance);
  },
};

function buildImports(env: Env): WebAssembly.Imports {
  return {
    // Expose only the minimum surface to the WASM module
    __wbindgen_placeholder__: {
      __wbindgen_throw: (ptr: number, len: number) => {
        throw new Error(`WASM error at ${ptr}:${len}`);
      },
    },
  };
}

async function handleWithWasm(
  _request: Request,
  _instance: WebAssembly.Instance
): Promise<Response> {
  return new Response("OK");
}
```

## Runtime WASM Loading with Digest Verification
When a WASM module must be fetched at runtime (e.g. versioned modules stored in R2), verify the SHA-256 digest before instantiation and reject any module that does not match.

```typescript
async function loadVerifiedWasm(
  url: string,
  expectedSha256Hex: string
): Promise<WebAssembly.Module> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`WASM fetch failed: ${response.status} ${url}`);
  }

  const bytes = await response.arrayBuffer();

  // Compute SHA-256 over the raw bytes
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  const actualHex = Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");

  if (!timingSafeEqual(actualHex, expectedSha256Hex)) {
    // Log the mismatch for incident response before throwing
    console.error(JSON.stringify({
      event: "WASM_INTEGRITY_FAILURE",
      url,
      expected: expectedSha256Hex,
      actual: actualHex,
    }));
    throw new Error("WASM integrity check failed — module rejected");
  }

  return WebAssembly.compile(bytes);
}

/** Constant-time string comparison to prevent timing oracle on digest values */
function timingSafeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) {
    diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return diff === 0;
}
```

## Storing Expected Digests as Worker Secrets
Expected SHA-256 hashes must be stored as Wrangler secrets — not in `wrangler.toml` or source code — so they are not visible to anyone with repository access.

```bash
# Store each expected digest as a named secret
wrangler secret put WASM_IMAGE_PROCESSOR_SHA256
# paste: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855

wrangler secret put WASM_CRYPTO_UTILS_SHA256
```

```typescript
// Runtime loading with per-module digest verification
export interface Env {
  WASM_BUCKET: R2Bucket;
  WASM_IMAGE_PROCESSOR_SHA256: string;
  WASM_CRYPTO_UTILS_SHA256: string;
}

async function loadWasmFromR2(
  bucket: R2Bucket,
  key: string,
  expectedDigest: string
): Promise<WebAssembly.Module> {
  const object = await bucket.get(key);
  if (!object) throw new Error(`WASM object not found: ${key}`);

  // R2 provides the stored MD5 via object.checksums — we add SHA-256 separately
  const bytes = await object.arrayBuffer();
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  const actualHex = Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");

  if (!timingSafeEqual(actualHex, expectedDigest)) {
    console.error(`WASM_INTEGRITY_FAILURE key=${key} expected=${expectedDigest} actual=${actualHex}`);
    throw new Error("WASM integrity check failed");
  }

  return WebAssembly.compile(bytes);
}
```

## Caching Verified Modules Across Requests
`WebAssembly.compile` is CPU-intensive. Cache the compiled `WebAssembly.Module` in a module-level variable after the first successful verification so subsequent isolate invocations reuse the compiled form.

```typescript
let imageProcessorModule: WebAssembly.Module | null = null;

async function getImageProcessorModule(env: Env): Promise<WebAssembly.Module> {
  if (imageProcessorModule) return imageProcessorModule;

  // Verify and compile on first use within this isolate lifetime
  const module = await loadWasmFromR2(
    env.WASM_BUCKET,
    "image-processor-v2.4.1.wasm",
    env.WASM_IMAGE_PROCESSOR_SHA256
  );

  imageProcessorModule = module;
  return module;
}

// Invalidate cached module on expected digest change (deploy triggers new isolate)
// No explicit cache invalidation needed — Wrangler deploys create fresh isolates
```

## Generating and Pinning Digests in CI
Compute and pin expected digests in CI so the secret value is deterministic and auditable. The CI step fails the build if the WASM file changes without a corresponding secret update.

```bash
#!/usr/bin/env bash
# ci/verify-wasm-digests.sh
set -euo pipefail

for wasm_file in src/*.wasm; do
  module_name=$(basename "$wasm_file" .wasm | tr '[:lower:]-' '[:upper:]_')
  expected_secret="WASM_${module_name}_SHA256"
  computed=$(sha256sum "$wasm_file" | awk '{print $1}')
  stored=$(wrangler secret get "$expected_secret" 2>/dev/null || echo "")

  if [[ "$computed" != "$stored" ]]; then
    echo "DIGEST MISMATCH for $wasm_file: computed=$computed stored=$stored"
    echo "Run: echo '$computed' | wrangler secret put $expected_secret"
    exit 1
  fi
done
echo "All WASM digests verified."
```

## Anti-patterns
- Fetching WASM from a public CDN URL without digest verification — a compromised CDN serves a malicious binary with no indication
- Storing expected digests in `wrangler.toml` or source code — repository read access exposes the pinned hash, which an attacker can update
- Using a non-constant-time comparison for digest strings — `===` on hex strings is measurably faster for matching prefixes and leaks information
- Skipping digest verification for "internal" R2 buckets — bucket misconfiguration or IAM errors can make them publicly writable
- Granting the WASM module access to the full `env` object as an import — expose only the specific functions the module needs

## Gotchas
- `WebAssembly.compile` is not available in the global scope of all Wrangler targets; test with `compatibility_date >= "2023-03-14"` for full WASM support
- Module-level cached `WebAssembly.Module` objects persist only for the lifetime of the isolate — Cloudflare may recycle isolates after minutes of inactivity, forcing a re-fetch
- R2 `object.checksums` provides the stored MD5 (for data integrity, not security); always compute your own SHA-256 over `arrayBuffer()` for supply chain purposes
- SHA-256 alone does not prove provenance — pair with Sigstore cosign attestations for stronger supply chain guarantees in high-risk deployments

## Verification
1. Bundle or fetch the known-good `.wasm` file, compute its SHA-256, and store it as a secret with `wrangler secret put`.
2. Deploy the Worker and verify it responds correctly to a test request.
3. Modify one byte of the `.wasm` file in R2 and re-trigger the Worker — confirm it returns an error and logs `WASM_INTEGRITY_FAILURE`.
4. Verify the CI `verify-wasm-digests.sh` script exits `1` when the compiled digest does not match the stored secret.

## Related
- [Supply Chain Integrity Sigstore](supply-chain-integrity-sigstore.md)
- [SLSA Supply Chain](slsa-supply-chain.md)
- [SRI Dynamic Workers Assets](sri-dynamic-workers-assets.md)
- [Workers Environment Variable Hygiene](workers-environment-variable-hygiene.md)
- [Wrangler CICD Secret Injection Hygiene](wrangler-cicd-secret-injection-hygiene.md)

## Sources
- https://developers.cloudflare.com/workers/runtime-apis/webassembly/
- https://developers.cloudflare.com/workers/configuration/wasm-modules/
- https://developer.mozilla.org/en-US/docs/WebAssembly/JavaScript_interface/compile_static
- https://www.w3.org/TR/CSP3/#match-url-to-source-expression (SRI concept applied to WASM)
- https://docs.sigstore.dev/cosign/overview/
