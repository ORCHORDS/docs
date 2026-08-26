# EU Right to Repair Directive — Digital Products

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your company manufactures or sells physical products with software
components (IoT devices, consumer electronics, appliances) in the EU.
You use software locks to prevent independent repair, do not make spare
parts available, or void warranties when third-party repairs are performed.
As of 31 July 2026, the EU Right to Repair Directive applies and these
practices are illegal.

## Context

The EU Right to Repair Directive (Directive (EU) 2024/1799) was adopted
in 2024 and applies across all 27 EU member states from 31 July 2026,
with every member state required to have it transposed into national law
by that date. The directive complements existing Ecodesign regulations and
the Consumer Sales Directive to create a comprehensive repair ecosystem.

## Scope

The directive's consumer law changes apply to business-to-consumer sales
of physical products, including those with digital elements (consumer
electronics preloaded with software, IoT devices, connected appliances).
It covers every "repairable" good already covered by Ecodesign rules:
phones, tablets, washing machines, dishwashers, vacuum cleaners, displays,
and more.

## Core obligations

### 1. Right to request repair

Consumers have the right to request repairs from the manufacturer at a
**reasonable price** and within a **reasonable timeframe**. Manufacturers
cannot refuse repair requests arbitrarily.

### 2. Software restrictions prohibited

Manufacturers cannot obstruct or impede repairs through:

- **Contractual clauses** that prohibit independent repair.
- **Hardware techniques** (e.g., parts pairing that disables functionality
  when a component is replaced by a non-OEM part).
- **Software techniques** (e.g., firmware that locks out third-party
  replacement parts, error messages designed to discourage repair).

The exception: restrictions are permitted only where "objectively
justifiable" — primarily safety or cybersecurity reasons.

### 3. Spare parts availability

Manufacturers must keep spare parts available for **years after a product
goes on sale** (specific periods vary by product category under Ecodesign
regulations — typically 7-10 years for major appliances).

### 4. Warranty extension for repair

When a consumer chooses **repair over replacement**, the warranty period
is extended by **12 months**. This incentivizes repair as the first option.

### 5. Repair information and tools

Manufacturers must provide:

- Repair manuals and technical documentation to independent repairers.
- Diagnostic tools and software necessary for repair.
- Firmware and software updates necessary to keep repaired products
  functional.

## Impact on software-embedded products

### Firmware and software updates

Manufacturers must continue providing software updates necessary for the
product to function, including security updates, for the expected lifespan
of the product. Withholding updates to force replacement violates both the
Right to Repair and the Consumer Sales Directive.

### Parts pairing

Software-enforced parts pairing — where a device refuses to function fully
with a non-OEM replacement part — is now restricted. Apple's approach of
degrading functionality when non-Apple parts are used will need to comply
with the "objectively justifiable" exception (safety/security only).

### Diagnostic access

Independent repairers must have access to the same diagnostic tools
available to authorized service providers. Proprietary diagnostic software
that is only available to OEM-authorized repairers is non-compliant.

## Anti-patterns

- **Software-enforced obsolescence** — using firmware updates to degrade
  performance of older devices or to disable functionality when warranty
  expires.
- **Parts pairing without justification** — serializing components and
  refusing to activate replacements when the safety/security justification
  is weak or absent.
- **Refusing post-repair warranty** — declining warranty obligations on
  a product because a previous repair was performed by an independent
  repairer (unless the repairer's work caused the defect).
- **Pricing repair above replacement** — quoting repair costs that exceed
  the cost of a replacement product to steer consumers toward purchasing
  new devices.

## Gotchas

- **Ecodesign interaction** — the Right to Repair Directive works alongside
  product-specific Ecodesign regulations. Spare parts availability periods
  and repairability scoring vary by product category.
- **Online marketplace obligations** — platforms facilitating B2C sales
  must inform consumers about repair options and their rights.
- **Repair scoring** — the EU is developing standardized repairability
  scores (similar to France's existing Indice de Réparabilité) that must
  be displayed at the point of sale.
- **B2B is excluded** — the directive applies to consumer (B2C) sales
  only. Business-to-business contracts remain governed by commercial law.

## Verification

- Software locks and parts pairing are reviewed and removed unless
  objectively justifiable for safety/security.
- Spare parts catalog and availability timeline are published.
- Repair manuals and diagnostic tools are accessible to independent
  repairers.
- Warranty extension of 12 months for repairs is implemented in warranty
  management systems.
- Software update commitment for the product's expected lifespan is
  documented.
- Pricing structure ensures repair is offered at a reasonable cost.

## Related

- `documentation/categories/compliance/eu-ai-act-article-5-prohibited-practices.md`
- `documentation/categories/issues/ai-watermarking-provenance-c2pa-2026.md`

## Source URLs (verified 2026-08-16)

- EU Right to Repair Directive — https://www.fieldfisher.com/en/insights/incoming-eu-right-to-repair-requirements-the-key-t
- Lewis Silkin analysis — https://www.lewissilkin.com/en/insights/2026/03/18/what-does-the-right-to-repair-directive-mean-for-your-business
- FixFirst explainer — https://fixfirst.io/blog/eu-right-to-repair-directive-explained
- EU Verify manufacturer guide — https://euverify.com/resource/eu-right-to-repair-directive/
