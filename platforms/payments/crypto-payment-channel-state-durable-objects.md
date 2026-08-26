# Crypto Payment Channel State Durable Objects

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

You are building a payment channel system on top of a UTXO or account-model
blockchain (e.g., Ethereum payment channels, Lightning-style off-chain channels,
or Solana state channels) and need to maintain consistent, low-latency channel
state at the edge — tracking balances, nonces, and dispute windows — without
running a centralized database that becomes a single point of failure.

Cloudflare Durable Objects give you one strongly-consistent in-memory actor per
channel, eliminating race conditions on concurrent balance updates and enabling
microsecond-latency reads for high-frequency micropayment flows.

## Context

Payment channels allow two parties to transact off-chain by locking funds on-chain
and exchanging signed state updates. The Durable Object acts as the authoritative
off-chain ledger for one channel instance:

- Receives payment update messages signed by both parties
- Validates signatures with the Web Crypto API
- Updates balances and increments the nonce
- Stores periodic checkpoints to Durable Object storage
- Triggers on-chain settlement when a close request arrives or a timeout elapses

Each channel gets its own Durable Object instance keyed by `channelId`. Workers
route messages to the correct instance using `env.CHANNEL.get(id)`.

## Durable Object: Channel State

```typescript
// channel-do.ts
import { DurableObject } from 'cloudflare:workers';

interface ChannelState {
  channelId: string;
  partyA: string;         // ethereum address or public key hex
  partyB: string;
  balanceA: bigint;       // in smallest unit (wei / lamport / satoshi)
  balanceB: bigint;
  nonce: number;
  status: 'open' | 'closing' | 'closed';
  disputeDeadline?: number; // unix timestamp ms
  fundedAmount: bigint;
  createdAt: number;
  updatedAt: number;
}

interface PaymentUpdate {
  nonce: number;
  balanceA: string;  // BigInt as string
  balanceB: string;
  sigA: string;      // hex signature from partyA
  sigB: string;      // hex signature from partyB
}

export class PaymentChannelDO extends DurableObject {
  private state: ChannelState | null = null;

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const action = url.pathname.split('/').pop();

    switch (action) {
      case 'open':    return this.handleOpen(request);
      case 'update':  return this.handleUpdate(request);
      case 'close':   return this.handleClose(request);
      case 'state':   return this.handleGetState();
      case 'dispute': return this.handleDispute(request);
      default:        return new Response('Unknown action', { status: 404 });
    }
  }

  private async loadState(): Promise<ChannelState | null> {
    if (this.state) return this.state;
    const stored = await this.ctx.storage.get<ChannelState>('channelState');
    this.state = stored ?? null;
    return this.state;
  }

  private async saveState(s: ChannelState): Promise<void> {
    this.state = s;
    await this.ctx.storage.put('channelState', s);
  }

  private async handleOpen(request: Request): Promise<Response> {
    const existing = await this.loadState();
    if (existing && existing.status !== 'closed') {
      return Response.json({ error: 'Channel already open' }, { status: 409 });
    }

    const body = await request.json() as {
      channelId: string;
      partyA: string;
      partyB: string;
      fundedAmount: string;
    };

    const s: ChannelState = {
      channelId: body.channelId,
      partyA: body.partyA,
      partyB: body.partyB,
      balanceA: BigInt(body.fundedAmount),
      balanceB: 0n,
      nonce: 0,
      status: 'open',
      fundedAmount: BigInt(body.fundedAmount),
      createdAt: Date.now(),
      updatedAt: Date.now(),
    };

    await this.saveState(s);
    return Response.json({ ok: true, nonce: 0 });
  }

  private async handleUpdate(request: Request): Promise<Response> {
    const s = await this.loadState();
    if (!s || s.status !== 'open') {
      return Response.json({ error: 'Channel not open' }, { status: 400 });
    }

    const update = await request.json() as PaymentUpdate;

    // Nonce must be strictly increasing
    if (update.nonce !== s.nonce + 1) {
      return Response.json({ error: `Expected nonce ${s.nonce + 1}` }, { status: 422 });
    }

    const newA = BigInt(update.balanceA);
    const newB = BigInt(update.balanceB);

    // Conservation: total must equal funded amount
    if (newA + newB !== s.fundedAmount) {
      return Response.json({ error: 'Balance sum mismatch' }, { status: 422 });
    }

    // Verify both signatures over the canonical state hash
    const stateHash = await computeStateHash(
      s.channelId, update.nonce, update.balanceA, update.balanceB
    );
    const [sigAValid, sigBValid] = await Promise.all([
      verifyEthSignature(stateHash, update.sigA, s.partyA),
      verifyEthSignature(stateHash, update.sigB, s.partyB),
    ]);

    if (!sigAValid || !sigBValid) {
      return Response.json({ error: 'Invalid signature(s)' }, { status: 400 });
    }

    s.balanceA = newA;
    s.balanceB = newB;
    s.nonce = update.nonce;
    s.updatedAt = Date.now();

    // Checkpoint every 100 updates to bound storage writes
    if (s.nonce % 100 === 0) {
      await this.saveState(s);
    } else {
      this.state = s; // keep hot in memory; alarm will flush
      await this.ctx.storage.setAlarm(Date.now() + 5_000); // flush in 5s
    }

    return Response.json({ ok: true, nonce: s.nonce });
  }

  async alarm(): Promise<void> {
    // Flush in-memory state to durable storage
    if (this.state) {
      await this.ctx.storage.put('channelState', this.state);
    }
  }

  private async handleClose(request: Request): Promise<Response> {
    const s = await this.loadState();
    if (!s || s.status !== 'open') {
      return Response.json({ error: 'Channel not open' }, { status: 400 });
    }

    const body = await request.json() as { requestedBy: string; finalUpdate?: PaymentUpdate };

    if (body.finalUpdate) {
      // Apply final state before closing
      const finalResp = await this.handleUpdate(
        new Request('https://x/update', {
          method: 'POST',
          body: JSON.stringify(body.finalUpdate),
        })
      );
      if (!finalResp.ok) return finalResp;
    }

    s.status = 'closing';
    s.disputeDeadline = Date.now() + 7 * 24 * 3600_000; // 7-day dispute window
    s.updatedAt = Date.now();
    await this.saveState(s);

    // Schedule alarm for dispute deadline
    await this.ctx.storage.setAlarm(s.disputeDeadline);

    return Response.json({
      ok: true,
      finalBalanceA: s.balanceA.toString(),
      finalBalanceB: s.balanceB.toString(),
      nonce: s.nonce,
      disputeDeadline: s.disputeDeadline,
    });
  }

  private async handleDispute(request: Request): Promise<Response> {
    const s = await this.loadState();
    if (!s || s.status !== 'closing') {
      return Response.json({ error: 'No active closing period' }, { status: 400 });
    }

    const body = await request.json() as { challengeUpdate: PaymentUpdate };
    const cu = body.challengeUpdate;

    if (cu.nonce <= s.nonce) {
      return Response.json({ error: 'Challenge nonce not higher than current' }, { status: 422 });
    }

    // Validate challenge signatures
    const stateHash = await computeStateHash(
      s.channelId, cu.nonce, cu.balanceA, cu.balanceB
    );
    const [sigAValid, sigBValid] = await Promise.all([
      verifyEthSignature(stateHash, cu.sigA, s.partyA),
      verifyEthSignature(stateHash, cu.sigB, s.partyB),
    ]);

    if (!sigAValid || !sigBValid) {
      return Response.json({ error: 'Invalid challenge signatures' }, { status: 400 });
    }

    // Update to higher nonce state
    s.balanceA = BigInt(cu.balanceA);
    s.balanceB = BigInt(cu.balanceB);
    s.nonce = cu.nonce;
    s.updatedAt = Date.now();
    await this.saveState(s);

    return Response.json({ ok: true, updatedNonce: s.nonce });
  }

  private async handleGetState(): Promise<Response> {
    const s = await this.loadState();
    if (!s) return Response.json({ error: 'Channel not found' }, { status: 404 });

    return Response.json({
      channelId: s.channelId,
      partyA: s.partyA,
      partyB: s.partyB,
      balanceA: s.balanceA.toString(),
      balanceB: s.balanceB.toString(),
      nonce: s.nonce,
      status: s.status,
      disputeDeadline: s.disputeDeadline,
    });
  }
}
```

## Cryptographic Helpers

```typescript
// crypto-helpers.ts

/** Compute keccak256-like state hash using SHA-256 (for non-Ethereum chains) */
async function computeStateHash(
  channelId: string,
  nonce: number,
  balanceA: string,
  balanceB: string
): Promise<Uint8Array> {
  const encoder = new TextEncoder();
  const data = encoder.encode(
    `${channelId}:${nonce}:${balanceA}:${balanceB}`
  );
  const hash = await crypto.subtle.digest('SHA-256', data);
  return new Uint8Array(hash);
}

/**
 * Verify an Ethereum personal_sign over a pre-hashed message.
 * Workers' Web Crypto supports ECDSA with P-256; for secp256k1 you must
 * use a WASM library (e.g., @noble/secp256k1 compiled for Workers).
 */
async function verifyEthSignature(
  messageHash: Uint8Array,
  signatureHex: string,
  expectedAddress: string
): Promise<boolean> {
  // In production: use @noble/secp256k1 in a Workers-compatible WASM bundle.
  // This stub shows the interface; replace with the real implementation.
  try {
    const { secp256k1 } = await import('@noble/secp256k1'); // bundled WASM
    const sigBytes = hexToBytes(signatureHex);
    const recovered = secp256k1.recoverPublicKey(messageHash, sigBytes.slice(0, 64), sigBytes[64]);
    const recoveredAddress = publicKeyToAddress(recovered);
    return recoveredAddress.toLowerCase() === expectedAddress.toLowerCase();
  } catch {
    return false;
  }
}

function hexToBytes(hex: string): Uint8Array {
  const clean = hex.startsWith('0x') ? hex.slice(2) : hex;
  return new Uint8Array(clean.match(/.{2}/g)!.map(b => parseInt(b, 16)));
}

function publicKeyToAddress(pubKey: Uint8Array): string {
  // keccak256 of pubKey[1:] -> last 20 bytes, checksum-encoded
  // Use a bundled keccak256 implementation
  throw new Error('Implement with bundled keccak256');
}
```

## Worker Router

```typescript
// index.ts
export { PaymentChannelDO } from './channel-do';

interface Env {
  CHANNEL: DurableObjectNamespace;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    // URL format: /channel/{channelId}/{action}
    const parts = url.pathname.split('/').filter(Boolean);
    if (parts[0] !== 'channel' || parts.length < 3) {
      return new Response('Bad request', { status: 400 });
    }

    const channelId = parts[1];
    const id = env.CHANNEL.idFromName(channelId);
    const stub = env.CHANNEL.get(id);

    // Forward to Durable Object with the action path
    const doUrl = new URL(request.url);
    doUrl.pathname = `/${parts[2]}`;
    return stub.fetch(new Request(doUrl.toString(), request));
  },
};
```

## Anti-patterns

- **Shared DO for all channels**: One Durable Object for all channel IDs becomes
  a bottleneck. Use `idFromName(channelId)` to get one DO per channel.
- **Writing to storage on every update**: High-frequency micropayment channels
  (100+ updates/second) will throttle on storage writes. Batch via alarms as
  shown above.
- **Trusting the client for nonce**: Always enforce server-side nonce monotonicity.
  A replayed lower-nonce update is a classic channel attack.
- **No dispute timeout**: Without an alarm-driven deadline, the `closing` state
  can linger indefinitely. Always set a `disputeDeadline` alarm.

## Gotchas

- Durable Object storage is limited to 128 KB per key. For channels with deep
  history, store only the latest checkpoint and an append log of nonces, not full
  update history.
- `secp256k1` is not available natively in the Web Crypto API. You must bundle a
  WASM implementation. `@noble/secp256k1` works in Workers; add it to your
  bundle with `wrangler build`.
- Durable Object alarms fire at-least-once. Your `alarm()` handler must be
  idempotent (safe to run twice).
- BigInt cannot be serialized with `JSON.stringify` by default. Convert to string
  before storing or transmitting; parse back on load.

## Verification

```bash
# Open a channel
curl -X POST https://your-worker.workers.dev/channel/ch_123/open \
  -H 'Content-Type: application/json' \
  -d '{"channelId":"ch_123","partyA":"0xABC...","partyB":"0xDEF...","fundedAmount":"1000000"}'

# Get channel state
curl https://your-worker.workers.dev/channel/ch_123/state

# Confirm nonce increments correctly after an update
curl -X POST https://your-worker.workers.dev/channel/ch_123/update \
  -H 'Content-Type: application/json' \
  -d '{"nonce":1,"balanceA":"900000","balanceB":"100000","sigA":"0x...","sigB":"0x..."}'
```

## Related

- `lightning-network-payments-workers.md` — Lightning Network integration
- `crypto-wallet-signature-verification-web-crypto-workers.md` — Sig verification
- `crypto-confirmation-depth-finality.md` — On-chain finality considerations
- `usdc-stablecoin-settlement-solana-webhooks.md` — On-chain settlement triggers

## Sources

- Cloudflare Durable Objects: https://developers.cloudflare.com/durable-objects/
- Ethereum State Channels: https://ethereum.org/en/developers/docs/scaling/state-channels/
- @noble/secp256k1: https://github.com/paulmillr/noble-secp256k1
- Connext Channel Architecture: https://docs.connext.network/
