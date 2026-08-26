# feature-flags-vendors

**Issue:** Compare feature flag vendors — LaunchDarkly, Split, Statsig, etc.
**Date:** 2026-08-09
**Status:** documented

## Symptom
You want a feature flag system. The vendors are: LaunchDarkly,
Split.io, Statsig, GrowthBook, Unleash, Flagsmith, Flipt.
Each claims to be the best. You don't know which to pick.

## Root cause
**Feature flag vendors have different strengths.** Pick
based on your needs.

**Source:** Vendor comparison (this entry).

## The comparison matrix

| Vendor | Self-hosted | Cloud | Free tier | Open source | Notes |
|---|---|---|---|---|---|
| **LaunchDarkly** | ❌ | ✅ | 2k seats | ❌ | Enterprise-focused |
| **Split.io** | ❌ | ✅ | Limited | ❌ | Feature experimentation |
| **Statsig** | ❌ | ✅ | 1M events/mo | ❌ | Developer-focused |
| **GrowthBook** | ✅ | ✅ | Unlimited | ✅ (MIT) | A/B testing focus |
| **Unleash** | ✅ | ✅ | Unlimited | ✅ (Apache 2.0) | Enterprise-grade |
| **Flagsmith** | ✅ | ✅ | Unlimited | ✅ (BSD) | Remote config |
| **Flipt** | ✅ | ❌ | N/A | ✅ (MPL 2.0) | Lightweight |
| **ConfigCat** | ❌ | ✅ | 10 flags | ❌ | Simple |
| **Optimizely** | ❌ | ✅ | Limited | ❌ | A/B testing focus |

## The "open source" choice

For most teams, **open source self-hosted** is the right
balance:
- **No vendor lock-in**
- **Free**
- **Full control**
- **Maintain your own (operational cost)**

Top picks:
- **GrowthBook** — A/B testing focus, modern UI
- **Unleash** — Mature, feature-rich, enterprise features
- **Flagsmith** — Remote config + flags

## The "managed cloud" choice

For teams without ops capacity:
- **LaunchDarkly** — Industry standard, enterprise features
- **Statsig** — Modern, dev-focused, free tier generous
- **ConfigCat** — Simple, cheap

## The "free tier" check

Always check the free tier limits:
- **LaunchDarkly:** 2k seats (free for 1 year)
- **Statsig:** 1M events/month
- **GrowthBook:** Unlimited (self-hosted)
- **Unleash:** Unlimited (self-hosted)
- **ConfigCat:** 10 flags (very limited)

## The "feature comparison"

| Feature | LaunchDarkly | GrowthBook | Unleash | Statsig |
|---|---|---|---|---|
| Boolean flags | ✅ | ✅ | ✅ | ✅ |
| Percentage rollout | ✅ | ✅ | ✅ | ✅ |
| A/B testing | Limited | ✅ | ❌ | ✅ |
| Targeting | ✅ | ✅ | ✅ | ✅ |
| Experimentation reports | Limited | ✅ | ❌ | ✅ |
| Audit log | ✅ | ✅ | ✅ | ✅ |
| SDKs | Many | Many | Many | Many |
| Edge support | ✅ | ✅ | ✅ | ✅ |
| On-prem | ❌ | ✅ | ✅ | ❌ |
| Cost | $$$ | Free | Free | $ (free tier) |

## The "use case" choice

### "I just need flags"
- **Unleash** (self-hosted) or **LaunchDarkly** (cloud)
- Simple, mature, no experimentation

### "I need A/B testing"
- **GrowthBook** or **Statsig**
- Built-in experimentation

### "I need on-prem"
- **GrowthBook** or **Unleash**
- Self-hosted, full control

### "I need enterprise features"
- **LaunchDarkly** (SOC 2, HIPAA, etc.)
- The enterprise standard

### "I need a quick start"
- **ConfigCat** or **Statsig**
- Free tier, no setup

## The "SDK" quality

For CF Workers, check SDK quality:
- **LaunchDarkly:** Official CF Workers SDK
- **GrowthBook:** JS SDK works
- **Unleash:** JS SDK works
- **Statsig:** Official CF Workers SDK

A vendor with a great CF Workers SDK is much easier to
integrate.

## The "data residency" check

For some apps (EU, government), data must stay in a
specific region:
- **Self-hosted:** Full control
- **Cloud vendors:** Some offer EU regions

Check before choosing.

## The "compliance" check

For regulated apps:
- **SOC 2:** Most cloud vendors
- **HIPAA:** LaunchDarkly, Statsig
- **GDPR:** Most vendors; check the DPA

## The "pricing" model

| Vendor | Pricing model |
|---|---|
| **LaunchDarkly** | Per seat (MAU) |
| **Statsig** | Per event |
| **GrowthBook** | Free (self-hosted); per MAU (cloud) |
| **Unleash** | Free (self-hosted); per MAU (cloud) |
| **ConfigCat** | Per flag |

For high-traffic apps, per-event pricing can be expensive.
For low-traffic apps, per-seat pricing is fine.

## The "migration" pattern

For switching vendors:
1. **Wrap the vendor SDK** in your own interface
2. **New code** uses your interface
3. **Migrate** the implementation when needed

```ts
// Your interface
interface FeatureFlagClient {
  isEnabled(name: string, context?: any): Promise<boolean>;
  getVariant(name: string, context?: any): Promise<string>;
}

// LaunchDarkly impl
class LaunchDarklyClient implements FeatureFlagClient {
  // ...
}

// GrowthBook impl
class GrowthBookClient implements FeatureFlagClient {
  // ...
}
```

Switching is just changing the impl.

## The "vendor lock-in" mitigation

For open source:
- **Self-host** or use the cloud
- **The data is yours**

For proprietary:
- **Use the vendor's export feature**
- **Plan an exit** before signing

## The "build vs buy" calculation

| Factor | Build | Buy |
|---|---|---|
| **Time to first flag** | 1-2 weeks | 1 hour |
| **Customization** | Unlimited | Limited |
| **Maintenance** | You | Vendor |
| **Cost (low traffic)** | Engineering time | Free tier |
| **Cost (high traffic)** | Engineering time | $$$ |
| **Risk** | Vendor-independent | Vendor lock-in |

For most teams, **buy (or self-host open source)** is the
right answer.

## Verification
- **Process:** Vendor is evaluated before adoption
- **Live:** The vendor is monitored (uptime, latency)
- **Audit:** Annual review of vendor costs

## Gotchas
- **The "vendor free tier is a trap" anti-pattern.** Free
  tier limits are low; high-traffic apps pay a lot.
- **The "vendor lock-in" anti-pattern.** Always have an
  exit plan.
- **The "vendor outage" anti-pattern.** A vendor outage
  can take down your flag evaluation. Have a fallback
  (default to off).
- **The "vendor SDK quality" anti-pattern.** A bad SDK
  causes bugs. Test the SDK before committing.
- **The "vendor data is sensitive" anti-pattern.** Flag
  data may include targeting rules (PII). Read the DPA.

## Related
- `feature-flags.md`
- `feature-flags-best-practices.md`
- `feature-flags-implementations.md`
- `feature-toggles-vs-branches.md`
- LaunchDarkly: https://launchdarkly.com/
- GrowthBook: https://www.growthbook.io/
- Unleash: https://www.getunleash.io/
- Statsig: https://statsig.com/
