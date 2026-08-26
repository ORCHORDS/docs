# zero-trust-device-posture

**Issue:** Enforcing device posture checks in Cloudflare Zero Trust Access policies
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Cloudflare Zero Trust device posture checks verify that a device meets security requirements (OS version, disk encryption, antivirus, certificate presence) before granting access to protected applications. Without posture checks, a user on a compromised or non-corporate device can still authenticate.

## Pattern / Solution

**Dashboard setup:**
1. Zero Trust → Settings → WARP Client → Device Posture → Add Check.
2. Select check type (examples below).
3. Add the check as a condition in an Access policy.

**Available posture check types:**

| Check | What it verifies |
|---|---|
| OS Version | Minimum OS version (macOS, Windows, iOS, Android) |
| Disk Encryption | FileVault (macOS) / BitLocker (Windows) enabled |
| Firewall | OS firewall enabled |
| Domain Joined | Windows machine joined to AD domain |
| Client Certificate | Device has a valid certificate from a trusted CA |
| Crowdstrike / SentinelOne / Tanium | EDR agent running and healthy |
| File Check | Specific file exists at a path |
| Serial Number | Device serial in an allowlist |
| Unique Client ID | WARP client ID in an allowlist |

**Example: Require disk encryption + minimum OS in Access policy:**
```
Access Application Policy:
  Rule: Allow
  Conditions:
    - Email domain: example.com           (identity)
    - Device Posture: Disk Encryption     (posture check 1)
    - Device Posture: OS Version ≥ 14.0   (posture check 2)
```

**Client certificate posture check setup:**
```bash
# 1. Generate CA (or use existing PKI)
openssl genrsa -out ca.key 4096
openssl req -new -x509 -key ca.key -out ca.crt -days 3650 \
  -subj "/CN=Corporate Device CA"

# 2. Upload CA to Cloudflare
curl -X POST "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/access/certificates" \
  -H "Authorization: Bearer $CF_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"name\": \"Corporate CA\", \"certificate\": \"$(cat ca.crt)\"}"

# 3. Issue device certificates via MDM (Jamf / Intune)
# and install to the system keychain
```

**Checking posture in a Worker (via Access JWT claims):**
```typescript
const { payload } = await jwtVerify(token, JWKS, { audience: AUD });
// Posture check results are included in custom claims if configured
const deviceId = payload['cf-access-device-id'] as string | undefined;
```

## Gotchas
- Device posture checks require **WARP client** to be installed and enrolled on the device — browser-only sessions cannot be checked for most posture types.
- Posture checks are re-evaluated periodically (every 5 minutes by default) while WARP is connected; they are not re-checked on every HTTP request.
- OS Version checks compare version strings lexicographically in some cases — test carefully for edge versions like `14.0` vs `14.1`.
- Client Certificate posture checks require the certificate to be in the **system keychain** (not user keychain) on macOS.
- Posture failures show a generic "Block" page; customize the block page in Zero Trust → Settings → Custom Pages.
- Cloudflare does not store the device's private key or personal data — posture is verified by the WARP client locally.
- Free plan supports basic posture checks; EDR integrations (CrowdStrike, etc.) require a paid Zero Trust plan.

## Related
- `cloudflare-teams-gateway.md`
- `zero-trust-access.md`
- `cloudflare-access-jwt-validation.md`
