# redis-streams

**Issue:** Need persistent, replayable message log with consumer groups in Redis
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Pub/Sub losing messages. Need multiple consumer groups processing the same stream at different rates.

## Pattern / Solution
XADD stream-name * field value to append with auto-generated ID. XREAD for simple consumption. XGROUP CREATE for consumer groups with acknowledged delivery. XREADGROUP to consume. XACK after processing. XPENDING to find unacknowledged messages for retry.

## Gotchas
- Streams grow indefinitely -- use MAXLEN option to cap size
- Consumer group must be created before consumers join
- Pending Entry List grows if messages not ACKed -- monitor with XPENDING and XAUTOCLAIM for dead consumers

## Related
- redis-pub-sub
- redis-data-structures
- database-change-data-capture
