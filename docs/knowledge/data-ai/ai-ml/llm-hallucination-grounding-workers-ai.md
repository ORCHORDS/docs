# LLM Hallucination Detection and Grounding with Workers AI

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your LLM returns answers that sound authoritative but are factually wrong or unsupported by the retrieved context. You need a grounding layer that (1) forces the model to cite source passages, (2) runs a verification pass that checks each claim against retrieved documents, and (3) flags or rewrites answers that cannot be substantiated—all within a Workers AI pipeline on Cloudflare.

## Context

Hallucination happens in two modes: intrinsic (model invents facts from parametric memory) and extrinsic (model ignores provided context). Grounding addresses both: retrieved passages from Vectorize constrain the answer space, and a secondary Workers AI "critic" call verifies each claim. The result is a structured JSON response with a grounded answer, citation list, and a confidence score indicating how much of the answer is supported.

---

## Grounded Generation Prompt

Force the model to answer exclusively from provided passages and emit bracketed citations.

```typescript
// grounded-prompt.ts
export interface Passage {
  id: string;
  text: string;
  source: string;
}

export function buildGroundedPrompt(
  question: string,
  passages: Passage[]
): { role: string; content: string }[] {
  const docs = passages
    .map((p, i) => `[${i + 1}] (id:${p.id} source:${p.source})\n${p.text}`)
    .join("\n\n");

  const system = `You are a grounded Q&A assistant. Answer the question using ONLY the provided documents.
Rules:
- Cite every factual claim with [N] where N is the document number.
- If the documents do not contain sufficient information, say "Insufficient grounding — I cannot answer this from the provided sources."
- Do NOT use any knowledge beyond the documents below.
- Keep your answer under 200 words.

Documents:
${docs}`;

  return [
    { role: "system", content: system },
    { role: "user", content: question }
  ];
}
```

---

## Claim Extraction Pass

After generating the answer, extract individual claims for verification.

```typescript
// claim-extractor.ts
export async function extractClaims(
  ai: Ai,
  answer: string
): Promise<string[]> {
  const result = await ai.run("@cf/mistral/mistral-7b-instruct-v0.1", {
    messages: [
      {
        role: "system",
        content: `Extract each distinct factual claim from the answer as a JSON array of strings.
Output ONLY the JSON array, nothing else. Example: ["Claim 1", "Claim 2"]`
      },
      { role: "user", content: answer }
    ],
    max_tokens: 256,
    temperature: 0
  }) as { response: string };

  try {
    return JSON.parse(result.response) as string[];
  } catch {
    // Fallback: split on sentence boundaries
    return answer.split(/(?<=[.!?])\s+/).filter(s => s.length > 20);
  }
}
```

---

## Critic: Claim Verification Against Passages

```typescript
// claim-verifier.ts
export type ClaimVerdict = "supported" | "contradicted" | "unverifiable";

export interface ClaimResult {
  claim: string;
  verdict: ClaimVerdict;
  supportingPassageId: string | null;
}

export async function verifyClaim(
  ai: Ai,
  claim: string,
  passages: Passage[]
): Promise<ClaimResult> {
  const docs = passages.map((p, i) => `[${i + 1}] ${p.text}`).join("\n\n");

  const result = await ai.run("@cf/mistral/mistral-7b-instruct-v0.1", {
    messages: [
      {
        role: "system",
        content: `Determine if the claim is supported, contradicted, or unverifiable based on the documents.
Respond with JSON only: {"verdict":"supported"|"contradicted"|"unverifiable","passageIndex":N|null}

Documents:
${docs}`
      },
      { role: "user", content: `Claim: ${claim}` }
    ],
    max_tokens: 64,
    temperature: 0
  }) as { response: string };

  try {
    const { verdict, passageIndex } = JSON.parse(result.response) as {
      verdict: ClaimVerdict;
      passageIndex: number | null;
    };
    return {
      claim,
      verdict,
      supportingPassageId: passageIndex != null ? passages[passageIndex - 1]?.id ?? null : null
    };
  } catch {
    return { claim, verdict: "unverifiable", supportingPassageId: null };
  }
}

export function computeGroundingScore(results: ClaimResult[]): number {
  if (results.length === 0) return 0;
  const supported = results.filter(r => r.verdict === "supported").length;
  return Math.round((supported / results.length) * 100);
}
```

---

## Pipeline Orchestration

```typescript
// grounding-pipeline.ts
export interface GroundedResponse {
  answer: string;
  groundingScore: number;          // 0–100, % of claims supported
  claims: ClaimResult[];
  citations: { id: string; source: string }[];
  flagged: boolean;                // true if score < threshold
}

const GROUNDING_THRESHOLD = 70;

export async function groundedQA(
  ai: Ai,
  vectorize: VectorizeIndex,
  question: string,
  embeddingModel = "@cf/baai/bge-base-en-v1.5"
): Promise<GroundedResponse> {
  // 1. Retrieve relevant passages from Vectorize
  const queryEmbedding = await ai.run(embeddingModel, { text: question }) as { data: number[][] };
  const results = await vectorize.query(queryEmbedding.data[0], { topK: 5, returnMetadata: "all" });
  const passages: Passage[] = results.matches.map(m => ({
    id: m.id,
    text: (m.metadata?.text as string) ?? "",
    source: (m.metadata?.source as string) ?? "unknown"
  }));

  // 2. Generate grounded answer
  const messages = buildGroundedPrompt(question, passages);
  const answerResult = await ai.run("@cf/mistral/mistral-7b-instruct-v0.1", {
    messages,
    max_tokens: 512,
    temperature: 0.2
  }) as { response: string };
  const answer = answerResult.response;

  // 3. Extract and verify claims in parallel
  const claims = await extractClaims(ai, answer);
  const verifiedClaims = await Promise.all(
    claims.map(c => verifyClaim(ai, c, passages))
  );

  // 4. Aggregate
  const groundingScore = computeGroundingScore(verifiedClaims);
  const cited = new Set(verifiedClaims.map(r => r.supportingPassageId).filter(Boolean));
  const citations = passages.filter(p => cited.has(p.id)).map(p => ({ id: p.id, source: p.source }));

  return {
    answer: groundingScore < GROUNDING_THRESHOLD
      ? `[Low confidence — ${groundingScore}% grounded] ${answer}`
      : answer,
    groundingScore,
    claims: verifiedClaims,
    citations,
    flagged: groundingScore < GROUNDING_THRESHOLD
  };
}
```

---

## Worker Entry Point

```typescript
// worker.ts
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const { question } = await req.json<{ question: string }>();
    if (!question?.trim()) return Response.json({ error: "question required" }, { status: 400 });

    const response = await groundedQA(env.AI, env.VECTORIZE, question);
    return Response.json(response);
  }
};
```

---

## Anti-patterns

- **Skipping the critic pass on short answers** — even a one-sentence answer can hallucinate a statistic; always verify claims.
- **Using the same model for generation and verification** — a model that hallucinated the claim often verifies it as true; use a separate model call with a stricter prompt.
- **Embedding the grounding score in the answer text** — expose it as a separate JSON field so clients can render it as a UI confidence indicator.
- **Running claim verification sequentially** — use `Promise.all` to parallelize; each verification is independent.
- **Hard-blocking on low scores** — prefer flagging with a warning; full suppression frustrates users when sources are genuinely sparse.

## Gotchas

- The critic pass adds one AI call per claim, which multiplies cost; cap claims at 5–6 per answer.
- JSON parsing of model responses fails occasionally — always wrap in try/catch with a sensible default.
- Vectorize returns up to 20 matches; more passages improve recall but inflate the context for both the generator and critic.
- "Unverifiable" does not mean wrong — it means the passages do not address the claim; log both categories separately.
- For time-sensitive facts (prices, live data), append a disclaimer regardless of grounding score because retrieval data may be stale.

## Verification

```bash
# Test with a question that has a clear answer in your index
curl -X POST https://your-worker.workers.dev/qa \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the capital of France?"}'
# Expected: groundingScore 80+, flagged: false, citations with passage ids

# Test with an out-of-scope question
curl -X POST https://your-worker.workers.dev/qa \
  -d '{"question": "What will the stock price be tomorrow?"}'
# Expected: answer begins "Insufficient grounding", groundingScore low, flagged: true
```

## Related

- `rag-hallucination-detection.md`
- `rag-citation-grounding.md`
- `rag-evaluation-metrics-faithfulness-testing.md`
- `llm-output-validation.md`
- `llm-as-judge-trace-evaluation.md`
- `retrieval-augmented-generation-d1-vectorize.md`

## Sources

- Vectorize query API: https://developers.cloudflare.com/vectorize/reference/client-api/
- Workers AI models: https://developers.cloudflare.com/workers-ai/models/
- RAG faithfulness evaluation: https://docs.ragas.io/en/stable/concepts/metrics/faithfulness.html
