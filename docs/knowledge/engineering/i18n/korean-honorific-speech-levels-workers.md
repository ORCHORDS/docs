# Korean Honorific Speech Levels on Cloudflare Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

A product serving Korean users generates server-side notifications and email copy at the edge. Korean has seven grammatical speech levels that alter verb endings, particles, and vocabulary throughout a sentence. Sending a casual *haeyoche* (해요체) message to a first-time enterprise customer, or an overly formal *hasipsyoche* (하십시오체) message in a casual consumer app, creates the wrong impression immediately. The speech level must be resolved from the user's account tier or age context before the string is assembled.

## Context

Korean speech-level selection (*gyeongeo*, 경어법) is grammatically pervasive: the verb ending, topic/subject particles, and even vocabulary items differ across levels. For product copy, two registers dominate: *haeyoche* (해요체, polite-informal) for B2C apps and *hasipsyoche* (하십시오체, formal polite) for B2B / enterprise. A third register, *banmal* (반말, informal), is used in youth-oriented or social products only when the user has explicitly configured a casual tone. Cloudflare Workers can select the correct message variant per-request using a small lookup table keyed by account tier, without shipping a large i18n library to the edge.

## Speech-Level Variant Store in KV

```typescript
// src/speech-levels.ts

export type SpeechLevel = "formal" | "polite" | "casual";

/**
 * Each message key stores three variants.
 * formal   → 하십시오체 (B2B / enterprise)
 * polite   → 해요체     (B2C default)
 * casual   → 반말       (opt-in social / youth product)
 */
export interface KoreanMessages {
  welcome:        Record<SpeechLevel, string>;
  save_success:   Record<SpeechLevel, string>;
  delete_confirm: Record<SpeechLevel, string>;
  logout_notice:  Record<SpeechLevel, string>;
}

export const KO_MESSAGES: KoreanMessages = {
  welcome: {
    formal: "환영합니다.",         // 하십시오체
    polite: "환영해요.",           // 해요체
    casual: "안녕!",               // 반말
  },
  save_success: {
    formal: "저장되었습니다.",
    polite: "저장됐어요.",
    casual: "저장했어.",
  },
  delete_confirm: {
    formal: "삭제하시겠습니까?",
    polite: "삭제할까요?",
    casual: "삭제할래?",
  },
  logout_notice: {
    formal: "로그아웃 되었습니다.",
    polite: "로그아웃됐어요.",
    casual: "로그아웃했어.",
  },
};

export function getKoreanMessage(
  key: keyof KoreanMessages,
  level: SpeechLevel
): string {
  return KO_MESSAGES[key][level];
}
```

## Account-Tier to Speech-Level Resolution at the Edge

```typescript
// src/worker.ts
import { getKoreanMessage, SpeechLevel } from "./speech-levels";

interface Env {
  USERS: KVNamespace;
}

interface UserProfile {
  accountTier: "enterprise" | "pro" | "free";
  speechLevelOverride?: SpeechLevel;
}

function resolveSpeechLevel(profile: UserProfile): SpeechLevel {
  // Explicit override always wins (user set it in profile preferences)
  if (profile.speechLevelOverride) {
    return profile.speechLevelOverride;
  }
  // Enterprise accounts default to formal
  if (profile.accountTier === "enterprise") {
    return "formal";
  }
  // All other tiers default to polite (해요체)
  return "polite";
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url    = new URL(request.url);
    const userId = url.searchParams.get("userId");
    const msgKey = url.searchParams.get("msg") as keyof typeof import("./speech-levels").KO_MESSAGES | null;

    if (!userId || !msgKey) {
      return new Response("Missing params", { status: 400 });
    }

    const raw = await env.USERS.get(userId, { type: "json" }) as UserProfile | null;
    if (!raw) {
      return new Response("User not found", { status: 404 });
    }

    const level   = resolveSpeechLevel(raw);
    const message = getKoreanMessage(msgKey, level);

    return new Response(JSON.stringify({ message, level }), {
      headers: { "Content-Type": "application/json; charset=utf-8" },
    });
  },
};
```

## Name Addressing with Korean Honorific Particles

```typescript
// src/korean-names.ts

/**
 * Korean name addressing rules:
 * - Append 님 (nim) after name for polite/formal registers.
 * - For formal contexts also prepend the title if known.
 * - No space between name and 님.
 *
 * The particle 이/가 (subject) and 을/를 (object) depend on
 * whether the preceding syllable ends in a consonant (받침).
 * Use Intl or a small batchim checker rather than a hardcoded list.
 */

/** Returns true if the last character of str ends in a consonant (받침 present). */
function hasBatchim(str: string): boolean {
  if (!str) return false;
  const code = str.charCodeAt(str.length - 1);
  if (code < 0xAC00 || code > 0xD7A3) return false; // not a Hangul syllable
  return (code - 0xAC00) % 28 !== 0;
}

export function formatKoreanName(
  name: string,
  level: "formal" | "polite" | "casual"
): string {
  if (level === "casual") return name; // 반말: bare name
  return `${name}님`;                  // 해요체 / 하십시오체: name + 님
}

export function subjectParticle(name: string): string {
  // 이 after consonant, 가 after vowel
  return hasBatchim(name) ? "이" : "가";
}

export function objectParticle(name: string): string {
  // 을 after consonant, 를 after vowel
  return hasBatchim(name) ? "을" : "를";
}

// Example usage:
// formatKoreanName("김민준", "polite") → "김민준님"
// subjectParticle("김민준")            → "이"  (ends in 준 which has batchim ㄴ)
// subjectParticle("이지아")            → "가"  (ends in 아 — no batchim)
```

## Anti-patterns

- Storing only one Korean string per message key and assuming `해요체` is always acceptable — enterprise customers notice immediately when addressed informally.
- Applying `님` to English names transliterated into Korean (`John님`) — the suffix still works grammatically but looks awkward; prefer English-locale strings for users whose profile name is in the Latin script.
- Hard-coding the particle `이/가` without checking 받침 — this produces grammatically incorrect sentences and signals to Korean readers that the product was not properly localized.

## Gotchas

- `반말` (casual) should only be activated via an explicit opt-in in user profile settings — defaulting to it based on inferred age or region is culturally inappropriate.
- Some honorific vocabulary items differ entirely across registers, not just verb endings (e.g., `있다` → `계시다` in respectful form for animate subjects). Purely suffix-swapping misses these and creates mixed-register sentences.

## Verification

```bash
# Seed KV with a test user profile
wrangler kv:key put --binding=USERS --local "u1" \
  '{"accountTier":"enterprise"}'

curl "http://localhost:8787?userId=u1&msg=welcome" | jq .
# Expected: { "message": "환영합니다.", "level": "formal" }

wrangler kv:key put --binding=USERS --local "u2" \
  '{"accountTier":"free","speechLevelOverride":"casual"}'

curl "http://localhost:8787?userId=u2&msg=save_success" | jq .
# Expected: { "message": "저장했어.", "level": "casual" }
```

## Related

- `i18n/japanese-honorifics-localization-workers.md`
- `i18n/personal-name-formatting-2026.md`
- `i18n/icu-messageformat-advanced.md`
- `i18n/translation-kv-caching-ttl-strategy.md`

## Sources

- https://developers.cloudflare.com/kv/
- https://www.korean.go.kr/front/onlineQna/onlineQnaView.do
- https://unicode.org/charts/PDF/UAC00.pdf
