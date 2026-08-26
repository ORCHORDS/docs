# metaplex-offchain-metadata-pitfall

**Issue:** NFT metadata silently corrupted when off-chain JSON 404s
**Date:** 2026-08-09
**Repo:** <your-org>/<your-repo> at main (PR #nft-metadata, issue #open-issue-nft)
**Author:** the platform team
**Status:** fixed (a sibling repo + the platform)

## Symptom
You mint an NFT on Solana. The on-chain transaction succeeds. The
NFT appears in the user's wallet. But the wallet shows:
- Name: "Unknown"
- Image: (placeholder grey square)
- Description: (empty)

The on-chain `data.uri` field is set correctly, but the JSON it
points to returns 404.

## Root cause
Metaplex Core (and Token Metadata) stores a `uri` field on-chain
that points to an **off-chain JSON file** with the full metadata:
```json
{
  "name": "the platform Genesis Pass",
  "symbol": "the platform",
  "image": "https://the domain/nft/wam-genesis.png",
  "description": "Founder-tier access pass",
  "attributes": [...]
}
```

The wallet (Phantom, Solflare, Magic Eden) fetches this JSON
**asynchronously** when displaying the NFT. If the JSON 404s:
- The wallet shows "Unknown" + placeholder image
- The user thinks the mint failed
- The metadata is silently lost
- The on-chain record is still valid (you can't "unmint" the NFT
  without burning it)

**Source:** Metaplex Core docs:
https://developers.metaplex.com/core/standards/json

> "The `uri` field is expected to point to a JSON file that
> conforms to the Metaplex JSON standard. ... If the JSON is
> unreachable, wallets will display a placeholder."

## Fix
Three layers:

### Layer 1: Ship the off-chain JSON
For every NFT mint, ship the corresponding JSON file at the URL
in the `uri` field BEFORE the mint transaction is confirmed.

```ts
// 1. Generate the metadata
const metadata = {
  name: 'the platform Genesis Pass',
  symbol: 'the platform',
  image: 'https://the domain/nft/wam-genesis.png',
  description: 'Founder-tier access pass',
  attributes: [
    { trait_type: 'Tier', value: 'Genesis' },
    { trait_type: 'Edition', value: '001/100' },
  ],
};

// 2. Upload to R2 / IPFS / Arweave
const url = await uploadToR2(metadata, `nft/${mintId}.json`);

// 3. Verify the URL is reachable
const probe = await fetch(url);
if (!probe.ok) throw new Error(`Metadata upload failed: ${probe.status}`);

// 4. THEN mint with the verified URL
await metaplex.create(...)
  .then(() => ({ uri: url }));
```

### Layer 2: Use a placeholder creator address
If you're testing or shipping a placeholder, use a clearly-fake
creator address that engineers can grep for:
```
PLACEHOLDER_PLATFORM_AUTHORITY_PUBKEY
```

When the real pubkey is available, swap it in. The placeholder
makes it obvious that the asset is a stub.

### Layer 3: Audit existing mints
For existing mints, run:
```bash
# Fetch all on-chain URIs and check 200 OK
for uri in $(solana account <mint> --output json | jq -r '.data.uri'); do
  status=$(curl -s -o /dev/null -w "%{http_code}" "$uri")
  echo "$status $uri"
done
```

Any non-200 needs the JSON shipped ASAP.

## Verification
- **Test:** `test/nft-metadata.test.ts > every minted NFT has a
  reachable off-chain JSON` — passes
- **Live:** Phantom wallet shows the NFT name + image within 2s
  of mint confirmation
- **Audit:** PR #nft-metadata ships a fix for 3 existing mints that had
  broken URIs

## Gotchas
- **The off-chain JSON is immutable once minted.** If you change
  the JSON after the mint, the wallet will show the new content
  (wallets re-fetch on every view). Use on-chain immutability for
  things that should NEVER change (e.g. "founder #001"), and
  off-chain mutability for things that can change (e.g. "current
  floor price").
- **Arweave is permanent but expensive.** IPFS is cheap but files
  can disappear. CF R2 + a public URL is the cheapest reliable
  option for the platform's case.
- **The image URL inside the JSON is also fetched asynchronously.**
  If the image 404s, the NFT shows the placeholder. Make sure
  the image is on a stable CDN (CF Images, R2 + custom domain).
- **Phantom vs Solflare cache differently.** Solflare caches for
  ~24h; Phantom re-fetches more aggressively. Test in both.
- **Don't put PII in the metadata.** The metadata is PUBLIC on
  the blockchain (via the URI). If you include a user email or
  physical address, it's leaked permanently.

## Related
- the platform issue #open-issue-nft
- the platform PR #nft-metadata (the fix)
- Metaplex JSON standard: https://developers.metaplex.com/core/standards/json
- CF R2 for NFT metadata: https://developers.cloudflare.com/r2/
