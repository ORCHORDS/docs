# Card BIN Lookup and Intelligent PSP Routing on Cloudflare Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Platforms using multiple payment processors need to route each card transaction to the PSP that offers the lowest cost or highest approval rate for that specific card type, issuing country, and network. A card BIN (Bank Identification Number — first 6 or 8 digits of the PAN) reveals the card network, type (debit/credit/prepaid), issuer country, and brand tier.

## Context
BIN lookup databases (Binlist, Mastercard BIN Lookup API, Visa BIN Attribute Sharing) map the BIN prefix to structured metadata. Cloudflare Workers cache BIN lookups in KV with a long TTL (BIN metadata changes infrequently), then run a routing algorithm to select the optimal PSP. This reduces interchange and scheme fees materially — e.g. routing EU-issued debit cards via an EU acquirer avoids cross-border interchange uplift.

## BIN Metadata Lookup with KV Caching

Cache BIN lookups in KV to avoid per-transaction external API calls.

```typescript
// bin-lookup.ts
import type { KVNamespace } from "@cloudflare/workers-types";

interface BinMetadata {
  bin: string;
  network: "visa" | "mastercard" | "amex" | "discover" | "unionpay" | "unknown";
  type: "credit" | "debit" | "prepaid" | "unknown";
  tier: "standard" | "gold" | "platinum" | "signature" | "unknown";
  issuerCountryCode: string;   // ISO 3166-1 alpha-2
  issuerName: string;
  regulated: boolean;           // Reg II / EU interchange cap applies
}

interface Env {
  BIN_KV: KVNamespace;
  BINLIST_API_KEY: string;     // e.g. Binlist.net pro key or Mastercard BIN API token
}

export async function lookupBin(rawPan: string, env: Env): Promise<BinMetadata> {
  const bin8 = rawPan.replace(/\D/g, "").slice(0, 8);
  const bin6 = bin8.slice(0, 6);

  // Try 8-digit first, fall back to 6-digit
  for (const bin of [bin8, bin6]) {
    const cached = await env.BIN_KV.get<BinMetadata>(`bin:${bin}`, "json");
    if (cached) return cached;
  }

  // Cache miss — call external BIN data provider
  const metadata = await fetchBinFromProvider(bin8, env.BINLIST_API_KEY);

  // Store with 30-day TTL; BIN data is stable
  await env.BIN_KV.put(`bin:${bin8}`, JSON.stringify(metadata), {
    expirationTtl: 2_592_000,
  });

  return metadata;
}

async function fetchBinFromProvider(bin: string, apiKey: string): Promise<BinMetadata> {
  // Binlist.net example — replace with Mastercard or Visa BIN API as needed
  const res = await fetch(`https://lookup.binlist.net/${bin}`, {
    headers: { "Accept-Version": "3", "X-API-Key": apiKey },
  });

  if (res.status === 404) {
    return unknownBin(bin);
  }
  if (!res.ok) throw new Error(`BIN lookup failed: ${res.status}`);

  const data = await res.json<{
    scheme: string;
    type: string;
    prepaid: boolean;
    country: { alpha2: string };
    bank: { name: string };
    brand?: string;
  }>();

  return {
    bin,
    network: normaliseNetwork(data.scheme),
    type: data.prepaid ? "prepaid" : normaliseType(data.type),
    tier: normaliseTier(data.brand ?? ""),
    issuerCountryCode: data.country?.alpha2 ?? "XX",
    issuerName: data.bank?.name ?? "Unknown",
    regulated: isRegulatedMarket(data.country?.alpha2 ?? ""),
  };
}

function unknownBin(bin: string): BinMetadata {
  return { bin, network: "unknown", type: "unknown", tier: "unknown",
           issuerCountryCode: "XX", issuerName: "Unknown", regulated: false };
}

function normaliseNetwork(scheme: string): BinMetadata["network"] {
  const s = scheme?.toLowerCase();
  if (s === "visa") return "visa";
  if (s === "mastercard") return "mastercard";
  if (s === "amex" || s === "american express") return "amex";
  if (s === "discover") return "discover";
  if (s === "unionpay") return "unionpay";
  return "unknown";
}

function normaliseType(type: string): BinMetadata["type"] {
  if (type?.toLowerCase() === "debit") return "debit";
  if (type?.toLowerCase() === "credit") return "credit";
  return "unknown";
}

function normaliseTier(brand: string): BinMetadata["tier"] {
  const b = brand.toLowerCase();
  if (b.includes("signature") || b.includes("infinite")) return "signature";
  if (b.includes("platinum")) return "platinum";
  if (b.includes("gold")) return "gold";
  return "standard";
}

function isRegulatedMarket(countryCode: string): boolean {
  // EU + EEA countries subject to EU interchange regulation
  const euEea = new Set(["AT","BE","BG","CY","CZ","DE","DK","EE","ES","FI","FR","GR",
    "HR","HU","IE","IT","LT","LU","LV","MT","NL","PL","PT","RO","SE","SI","SK",
    "IS","LI","NO"]);
  return euEea.has(countryCode);
}
```

## PSP Routing Rules Engine

Select the optimal PSP based on BIN metadata, transaction amount, and configured routing preferences.

```typescript
// psp-router.ts
import type { BinMetadata } from "./bin-lookup";

type PspId = "stripe" | "adyen" | "braintree" | "square";

interface RoutingContext {
  bin: BinMetadata;
  amountMinor: number;
  currency: string;
  merchantCountryCode: string;   // ISO 3166-1 alpha-2
}

interface RoutingDecision {
  psp: PspId;
  reason: string;
  estimatedInterchangeBps: number;
}

const ROUTING_RULES: Array<{
  name: string;
  match: (ctx: RoutingContext) => boolean;
  psp: PspId;
  reason: string;
  estimatedInterchangeBps: number;
}> = [
  {
    name: "eu_regulated_debit",
    // EU-issued regulated debit via EU acquirer → capped at 20 bps
    match: (ctx) => ctx.bin.regulated && ctx.bin.type === "debit" && ctx.merchantCountryCode in euSet,
    psp: "adyen",
    reason: "eu_regulated_debit_lower_interchange",
    estimatedInterchangeBps: 20,
  },
  {
    name: "eu_regulated_credit",
    match: (ctx) => ctx.bin.regulated && ctx.bin.type === "credit" && ctx.merchantCountryCode in euSet,
    psp: "adyen",
    reason: "eu_regulated_credit_lower_interchange",
    estimatedInterchangeBps: 30,
  },
  {
    name: "high_value_premium",
    // High-value premium cards → route to PSP with best approval rate for this segment
    match: (ctx) => ctx.amountMinor >= 50_000 && ctx.bin.tier === "signature",
    psp: "stripe",
    reason: "high_value_premium_card_approval_optimisation",
    estimatedInterchangeBps: 220,
  },
  {
    name: "prepaid_block_or_stripe",
    match: (ctx) => ctx.bin.type === "prepaid",
    psp: "stripe",
    reason: "prepaid_radar_fraud_controls",
    estimatedInterchangeBps: 180,
  },
  {
    name: "default",
    match: () => true,
    psp: "stripe",
    reason: "default_route",
    estimatedInterchangeBps: 160,
  },
];

const euSet: Record<string, true> = Object.fromEntries(
  ["AT","BE","BG","CY","CZ","DE","DK","EE","ES","FI","FR","GR","HR","HU","IE","IT",
   "LT","LU","LV","MT","NL","PL","PT","RO","SE","SI","SK"].map((c) => [c, true])
);

export function routeTransaction(ctx: RoutingContext): RoutingDecision {
  for (const rule of ROUTING_RULES) {
    if (rule.match(ctx)) {
      return { psp: rule.psp, reason: rule.reason, estimatedInterchangeBps: rule.estimatedInterchangeBps };
    }
  }
  return { psp: "stripe", reason: "fallback", estimatedInterchangeBps: 160 };
}
```

## Integrating Lookup and Routing at Payment Intake

```typescript
// payment-router-handler.ts
import type { KVNamespace, D1Database } from "@cloudflare/workers-types";
import { lookupBin } from "./bin-lookup";
import { routeTransaction } from "./psp-router";

interface Env {
  BIN_KV: KVNamespace;
  BINLIST_API_KEY: string;
  DB: D1Database;
}

export async function routePaymentRequest(req: Request, env: Env): Promise<Response> {
  const { pan, amountMinor, currency, merchantCountryCode } = await req.json<{
    pan: string;
    amountMinor: number;
    currency: string;
    merchantCountryCode: string;
  }>();

  const bin = await lookupBin(pan, env);
  const decision = routeTransaction({ bin, amountMinor, currency, merchantCountryCode });

  // Log routing decision for analytics
  await env.DB.prepare(
    `INSERT INTO routing_log (bin, psp, reason, estimated_interchange_bps,
       amount_minor, currency, merchant_country, created_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)`
  )
    .bind(bin.bin, decision.psp, decision.reason, decision.estimatedInterchangeBps,
          amountMinor, currency, merchantCountryCode)
    .run();

  return Response.json({
    selectedPsp: decision.psp,
    reason: decision.reason,
    binMeta: {
      network: bin.network,
      type: bin.type,
      tier: bin.tier,
      issuerCountry: bin.issuerCountryCode,
      regulated: bin.regulated,
    },
  });
}
```

## Anti-patterns
- Using the BIN for fraud decisions alone — BIN is not a fraud signal; it is a routing signal. Use Stripe Radar, Adyen DataMixer, or a velocity check layer for fraud.
- Storing full PANs to perform BIN lookup — only extract the first 6–8 digits from the raw PAN and discard the rest immediately; never log or store the full PAN.
- Caching BIN metadata indefinitely without TTL — card programs change issuer, network, or tier; use a 30-day TTL and allow manual cache busting.
- Hardcoding BIN ranges — ranges shift as networks issue new IINs; always use a maintained BIN database.

## Gotchas
- 8-digit BINs (IINs) were introduced by ISO/IEC 7812-1:2017; some older providers return only 6-digit data. Prefer 8-digit lookup with 6-digit fallback.
- Corporate and government cards often have non-standard tier strings — treat unrecognised tiers as `"standard"` rather than throwing an error.
- Amex cards use 15 digits, not 16; `pan.slice(0,8)` still works correctly.
- KV read latency is typically < 5 ms in the same region; for globally distributed checkout, ensure BIN KV is replicated globally (Cloudflare KV replicates by default).

## Verification
1. Seed KV with a synthetic BIN entry `48213500` as EU Visa debit regulated.
2. POST `{"pan":"4821350012345678","amountMinor":2000,"currency":"EUR","merchantCountryCode":"DE"}` — expect `selectedPsp: "adyen"`.
3. POST with `amountMinor: 75000` and a signature-tier BIN — expect `selectedPsp: "stripe"`.
4. Confirm `routing_log` D1 table rows for both requests.
5. Verify KV TTL: `wrangler kv key get --namespace-id=<id> "bin:48213500"` — check `expiration` field.

## Related
- [Payment Orchestration Multi-PSP Routing](payment-orchestration-multi-psp-routing.md)
- [Gateway Failover and Circuit Breakers](gateway-failover-circuit-breakers.md)
- [Interchange Fee Optimization](interchange-fee-optimization.md)
- [Network Tokenization vs Vault Tokens](network-tokenization-vs-vault-tokens.md)
- [PSD2 SCA Exemption Strategies](psd2-sca-exemption-strategies.md)

## Sources
- ISO/IEC 7812-1:2017 (IIN standard): https://www.iso.org/standard/70484.html
- Binlist.net BIN lookup API: https://binlist.net/
- Mastercard BIN Lookup API: https://developer.mastercard.com/bin-lookup/
- EU Interchange Fee Regulation 2015/751: https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32015R0751
