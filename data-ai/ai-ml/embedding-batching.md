# embedding-batching

**Issue:** Batching embedding requests to maximize throughput and minimize cost
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Single-item embedding calls waste API capacity and increase per-token cost.

## Pattern / Solution
```python
import asyncio
from collections import deque

class EmbeddingBatcher:
    def __init__(self, client, batch_size=100, flush_interval=0.1):
        self.queue = deque()
        self.batch_size = batch_size
        self.flush_interval = flush_interval

    async def embed(self, text: str) -> list[float]:
        future = asyncio.get_event_loop().create_future()
        self.queue.append((text, future))
        if len(self.queue) >= self.batch_size:
            await self._flush()
        return await future

    async def _flush(self):
        batch = [self.queue.popleft() for _ in range(min(self.batch_size, len(self.queue)))]
        texts, futures = zip(*batch)
        embeddings = await embed_batch(list(texts))
        for f, emb in zip(futures, embeddings):
            f.set_result(emb)
```

## Gotchas
- Flush timeout prevents stuck batches when traffic is low
- Sort inputs by length for tighter batching (reduces padding)
- Use OpenAI Batch API for offline indexing — 50% cheaper

## Related
- `embedding-generation-patterns.md`
- `llm-batch-processing.md`
