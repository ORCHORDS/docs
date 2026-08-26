# Android NFC Workers Contactless Authentication

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

You need tap-to-authenticate with NFC cards or tags backed by a Cloudflare Workers
NDEF-verification endpoint. The challenge: raw NDEF payloads arrive on the Android
foreground dispatch thread, but token exchange and session creation must happen
over a signed request to Workers without blocking the NFC reader.

---

## Context

Android exposes NFC via `NfcAdapter.enableForegroundDispatch` / `ACTION_NDEF_DISCOVERED`
intents. The tag payload (UID or NDEF record bytes) must be sent to a Workers endpoint
that verifies the challenge-response, stores the session in KV, and returns a JWT.
The flow must complete inside the NFC reader's 2-second timeout window or the tag
connection drops.

Stack:
- Android Kotlin / Jetpack Compose
- `android.nfc.*`
- Cloudflare Workers (TypeScript) + KV + D1

---

## 1. Foreground Dispatch Setup (Kotlin)

```kotlin
class NfcAuthActivity : ComponentActivity() {
    private lateinit var nfcAdapter: NfcAdapter
    private val pendingIntent by lazy {
        PendingIntent.getActivity(
            this, 0,
            Intent(this, javaClass).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_MUTABLE
        )
    }

    override fun onResume() {
        super.onResume()
        nfcAdapter = NfcAdapter.getDefaultAdapter(this)
        nfcAdapter.enableForegroundDispatch(
            this, pendingIntent,
            arrayOf(IntentFilter(NfcAdapter.ACTION_NDEF_DISCOVERED)),
            arrayOf(arrayOf(NfcF.requestedTechList()))
        )
    }

    override fun onPause() {
        super.onPause()
        nfcAdapter.disableForegroundDispatch(this)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        if (intent.action == NfcAdapter.ACTION_NDEF_DISCOVERED) {
            val tag = IntentCompat.getParcelableExtra(intent, NfcAdapter.EXTRA_TAG, Tag::class.java)
            tag?.let { handleNfcTag(it) }
        }
    }
}
```

---

## 2. Extracting NDEF Payload and UID

```kotlin
fun handleNfcTag(tag: Tag) {
    val uid = tag.id.toHexString()          // card UID as hex
    val ndef = Ndef.get(tag)
    var ndefPayload: ByteArray? = null

    ndef?.let {
        it.connect()
        val message = it.ndefMessage
        ndefPayload = message?.records?.firstOrNull()?.payload
        it.close()
    }

    viewModel.authenticateWithNfc(uid, ndefPayload)
}

fun ByteArray.toHexString() = joinToString("") { "%02x".format(it) }
```

---

## 3. Workers Auth Endpoint

```typescript
// workers/src/nfc-auth.ts
import { Hono } from 'hono'
import { sign } from '@tsndr/cloudflare-worker-jwt'

interface Env {
  NFC_SESSIONS: KVNamespace
  DB: D1Database
  JWT_SECRET: string
}

const app = new Hono<{ Bindings: Env }>()

app.post('/nfc/authenticate', async (c) => {
  const { uid, ndefPayload, challengeToken } = await c.req.json<{
    uid: string
    ndefPayload: string | null
    challengeToken: string
  }>()

  // Verify challenge token was issued by us
  const storedChallenge = await c.env.NFC_SESSIONS.get(`challenge:${uid}`)
  if (!storedChallenge || storedChallenge !== challengeToken) {
    return c.json({ error: 'invalid_challenge' }, 401)
  }

  // Look up registered card in D1
  const card = await c.env.DB.prepare(
    'SELECT user_id, card_name FROM nfc_cards WHERE uid = ? AND active = 1'
  ).bind(uid).first<{ user_id: string; card_name: string }>()

  if (!card) {
    return c.json({ error: 'card_not_registered' }, 403)
  }

  // Issue JWT
  const token = await sign(
    { sub: card.user_id, iat: Date.now() / 1000, exp: Date.now() / 1000 + 3600 },
    c.env.JWT_SECRET
  )

  // Invalidate challenge
  await c.env.NFC_SESSIONS.delete(`challenge:${uid}`)

  return c.json({ token, userId: card.user_id })
})

app.post('/nfc/challenge', async (c) => {
  const { uid } = await c.req.json<{ uid: string }>()
  const challenge = crypto.randomUUID()
  await c.env.NFC_SESSIONS.put(`challenge:${uid}`, challenge, { expirationTtl: 30 })
  return c.json({ challenge })
})

export default app
```

---

## 4. ViewModel — Challenge-Response Flow (Kotlin)

```kotlin
class NfcAuthViewModel(private val api: NfcAuthApi) : ViewModel() {
    private val _state = MutableStateFlow<NfcState>(NfcState.Idle)
    val state: StateFlow<NfcState> = _state.asStateFlow()

    fun authenticateWithNfc(uid: String, ndefPayload: ByteArray?) {
        viewModelScope.launch {
            _state.value = NfcState.Authenticating
            try {
                // 1. Fetch challenge (must happen before NFC timeout)
                val challenge = api.requestChallenge(uid)

                // 2. Exchange UID + payload + challenge for JWT
                val result = api.authenticate(
                    uid = uid,
                    ndefPayload = ndefPayload?.toHexString(),
                    challengeToken = challenge.challenge
                )
                _state.value = NfcState.Success(result.token, result.userId)
            } catch (e: Exception) {
                _state.value = NfcState.Error(e.message ?: "NFC auth failed")
            }
        }
    }
}

sealed class NfcState {
    object Idle : NfcState()
    object Authenticating : NfcState()
    data class Success(val token: String, val userId: String) : NfcState()
    data class Error(val message: String) : NfcState()
}
```

---

## 5. D1 Schema for Card Registry

```sql
-- workers/schema.sql
CREATE TABLE IF NOT EXISTS nfc_cards (
  id        TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  uid       TEXT NOT NULL UNIQUE,
  user_id   TEXT NOT NULL,
  card_name TEXT NOT NULL,
  active    INTEGER NOT NULL DEFAULT 1,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_nfc_cards_uid ON nfc_cards(uid);
CREATE INDEX IF NOT EXISTS idx_nfc_cards_user ON nfc_cards(user_id);
```

---

## Anti-patterns

- **Blocking the NFC thread**: do NOT make network calls on `onNewIntent` directly;
  always dispatch to a coroutine / background thread immediately.
- **Trusting UID alone**: NFC UIDs can be cloned; always require a server-issued
  challenge that ties the request to a time window.
- **Storing the JWT in SharedPreferences**: use Android Keystore-backed EncryptedSharedPreferences
  or `react-native-keychain` equivalent.
- **Long-lived KV challenges**: set `expirationTtl` to 30 seconds maximum — any longer
  widens the replay window.

---

## Gotchas

- `enableForegroundDispatch` must be called in `onResume`, not `onCreate`; calling it
  too early means the activity may not be in the foreground when a tag is scanned.
- On Android 12+ (API 31), `PendingIntent` must declare `FLAG_MUTABLE` or
  `FLAG_IMMUTABLE` explicitly; omitting it throws `IllegalArgumentException`.
- Some NFC cards (MIFARE Classic) are not supported on all Android devices;
  check `NfcAdapter.isEnabled()` and handle gracefully.
- Workers KV eventual consistency: in rare cases the challenge may not be readable
  at the nearest PoP immediately after write; add a 100 ms retry with exponential
  backoff.

---

## Verification

```bash
# 1. Confirm Workers schema deployed
wrangler d1 execute DB --remote --command "SELECT COUNT(*) FROM nfc_cards"

# 2. End-to-end manual test
curl -X POST https://api.example.com/nfc/challenge \
  -H "Content-Type: application/json" \
  -d '{"uid":"04a3b2c1d0e5f6"}'

curl -X POST https://api.example.com/nfc/authenticate \
  -H "Content-Type: application/json" \
  -d '{"uid":"04a3b2c1d0e5f6","ndefPayload":null,"challengeToken":"<from-above>"}'

# 3. Android unit test
./gradlew :app:testDebugUnitTest --tests "NfcAuthViewModelTest"
```

---

## Related

- `android-keystore-biometrics.md`
- `android-credential-manager-passkey-migration.md`
- `mobile-webauthn-workers-credential-storage.md`
- `capacitor-workers-biometric-webauthn.md`
- `android-network-security-config.md`

---

## Sources

- Android NFC developer guide: https://developer.android.com/guide/topics/connectivity/nfc
- Cloudflare KV API: https://developers.cloudflare.com/kv/
- Cloudflare D1: https://developers.cloudflare.com/d1/
- NFC Forum NDEF spec: https://nfc-forum.org/our-work/specification-releases/
