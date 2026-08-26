# data-i18n-dynamic-values

**Issue:** A locale-bootstrap system walks the DOM and replaces element text based on `data-i18n` attributes. Someone tagged a live countdown timer and a fetched username with the attribute; the bootstrap then overwrote the REAL runtime values ("14:32", "@user") with locale label strings on every re-translation pass. Visual chaos, data replaced by keys. Observed on example project (example-org/example-repo).

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The failure mechanism

1. **Static-translation systems assume their targets are static** — the bootstrap treats every `data-i18n` element as "text comes from the locale file, always".
2. **Dynamic data has no locale key** — timers, usernames, fetched counts, prices; tagging them hands their text nodes to the translator.
3. **Re-translation passes repeat the damage** — language switching or late bootstrap re-runs replace whatever the app rendered since.
4. **The bug is intermittent-looking** — it appears only after data loads AND a translation pass runs, so it skips local testing and surfaces in production.
5. **Wrappers make it worse** — tagging a container instead of a leaf hands the whole subtree to the translator.

## The rules

1. **`data-i18n` ONLY on static chrome** — labels, headings, buttons, placeholders: elements whose text is known at build time.
2. **Dynamic values get structure, not translation:** `<span data-i18n="minutes-label"></span> <span class="js-value"></span>` — translate the label, never the value.
3. **Interpolation belongs in the locale layer** — `t('welcome', {name})` formats the translated template around the runtime value; the value itself is never a target.
4. **Never tag containers** — attribute goes on the exact leaf text node.
5. **Audit passes should grep `data-i18n` elements that also carry dynamic classes/handlers** (`js-`, `bind-`, IDs of live regions) — that's the bug signature.

## Detection checklist

1. Does the element's text change after data fetch? → it must NOT carry `data-i18n`.
2. Does the element update on a timer/interval? → same rule.
3. After a language switch, do fetched values survive? — if they turn into keys/labels, a dynamic node got tagged.
4. Are formatted numbers/dates rendered via `Intl.*` into a plain node? → keep translation and formatting on separate nodes.
5. Is the attribute on a wrapper with children? → move it to each static leaf.

## Related

- `i18n-linting-static-analysis-2026.md` (lint rules that can catch tagged dynamic nodes)
- `../frontend/build-time-env-baking-chunk-hash.md` (same shape: build-time system vs runtime data)
