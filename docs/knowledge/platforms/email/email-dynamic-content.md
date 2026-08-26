# email-dynamic-content

**Issue:** Rendering different email content blocks based on recipient attributes
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Single email template needs to show different content to different segments without sending separate campaigns.

## Pattern / Solution
Conditional blocks in Liquid:
```liquid
{% if user.plan == 'free' %}
  <p>Upgrade to Pro to unlock all features.</p>
{% elsif user.plan == 'pro' %}
  <p>You're on Pro! Here's what's new this month.</p>
{% endif %}

{% if user.country == 'US' %}
  <p>Domestic shipping included.</p>
{% else %}
  <p>International shipping rates apply.</p>
{% endif %}
```

For loop over items:
```liquid
{% for item in recentItems limit:3 %}
  <li>{{ item.name }} - {{ item.price | money }}</li>
{% endfor %}
```

## Gotchas
- Rendering time scales with template complexity; precompile and cache where possible.
- Dynamic images (product photos, personalized banners) must be hosted reliably; 404 images look broken.
- Test every branch of conditional logic before shipping.

## Related
- email-personalization-patterns, liquid-template-email, email-template-versioning, drip-campaign-architecture
