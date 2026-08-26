# Zero Trust WARP Device Enrollment Automation

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

You need to programmatically enroll or re-enroll WARP devices — for example, as part of
an MDM (Mobile Device Management) pipeline, an onboarding script, or a fleet management
system — without requiring users to manually open the WARP client and log in each time.
You also need to enforce enrollment policies (device posture, identity) and audit which
devices are active.

## Context

Cloudflare WARP is the client-side component of Zero Trust. Enrollment means the client
has authenticated against your Zero Trust organisation and is routing DNS and network
traffic through Cloudflare Gateway. Automation operates at two levels:

1. **MDM pre-configuration**: deploy the `mdm.xml` (Windows) or `.mobileconfig` (macOS/iOS)
   or managed Android config via your MDM tool before the user ever opens WARP. WARP reads
   these profiles and auto-enrolls on first launch.
2. **API-driven lifecycle management**: query enrolled devices, revoke enrollments, and
   list posture check results via the Cloudflare Zero Trust REST API.

Authentication for the API uses an API token with the `Zero Trust: Read` + `Zero Trust: Edit`
permissions scoped to your account.

---

## 1. MDM Pre-Configuration for macOS (mobileconfig)

Generate a `.mobileconfig` payload that auto-enrolls all managed Macs into your Zero Trust
org without any user interaction:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>PayloadContent</key>
  <array>
    <dict>
      <key>PayloadType</key>
      <string>com.cloudflare.warp</string>
      <key>PayloadVersion</key>
      <integer>1</integer>
      <key>PayloadIdentifier</key>
      <string>com.example.cloudflare-warp</string>
      <key>PayloadUUID</key>
      <string>YOUR-UUID-HERE</string>
      <key>organization</key>
      <string>your-org-name.cloudflareaccess.com</string>
      <key>auto_connect</key>
      <integer>1</integer>
      <key>switch_locked</key>
      <false/>
      <key>service_mode</key>
      <string>warp</string>
      <key>support_url</key>
      <string>https://support.example.com</string>
    </dict>
  </array>
  <key>PayloadDisplayName</key>
  <string>Cloudflare WARP Zero Trust</string>
  <key>PayloadIdentifier</key>
  <string>com.example.mdm.warp</string>
  <key>PayloadType</key>
  <string>Configuration</string>
  <key>PayloadUUID</key>
  <string>YOUR-PROFILE-UUID</string>
  <key>PayloadVersion</key>
  <integer>1</integer>
</dict>
</plist>
```

Deploy via Jamf, Mosyle, or Kandji as a Custom Profile. On first WARP launch the client
reads the profile and opens an IdP login prompt (or skips it if `auth_client_id` /
`auth_client_secret` Service Auth is configured).

---

## 2. Windows MDM (mdm.xml)

```xml
<WARPManagedSettings>
  <organization>your-org-name.cloudflareaccess.com</organization>
  <auto_connect>1</auto_connect>
  <switch_locked>false</switch_locked>
  <service_mode>warp</service_mode>
  <onboarding>false</onboarding>
</WARPManagedSettings>
```

Place at `C:\ProgramData\Cloudflare\mdm.xml` via Group Policy or Intune Win32 app
deployment. Restart the WARP service for the configuration to take effect.

---

## 3. API: List Enrolled Devices

```typescript
// workers-script or Node.js automation
const ACCOUNT_ID = 'your-account-id';
const API_TOKEN  = process.env.CF_API_TOKEN!;

interface WARPDevice {
  id: string;
  name: string;
  user: { email: string };
  last_seen: string;
  revoked: boolean;
  serial_number: string;
}

async function listDevices(page = 1, perPage = 50): Promise<WARPDevice[]> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/devices?page=${page}&per_page=${perPage}`,
    { headers: { Authorization: `Bearer ${API_TOKEN}` } }
  );
  const json = await res.json<{ result: WARPDevice[]; success: boolean }>();
  if (!json.success) throw new Error('API error');
  return json.result;
}

// Paginate all devices
async function allDevices(): Promise<WARPDevice[]> {
  const devices: WARPDevice[] = [];
  let page = 1;
  while (true) {
    const batch = await listDevices(page);
    devices.push(...batch);
    if (batch.length < 50) break;
    page++;
  }
  return devices;
}
```

---

## 4. API: Revoke a Device Enrollment

When an employee departs or a device is lost, revoke its enrollment to immediately cut
Zero Trust access:

```typescript
async function revokeDevice(deviceId: string): Promise<void> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/devices/${deviceId}/revoke`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${API_TOKEN}`,
        'Content-Type': 'application/json',
      },
    }
  );
  const json = await res.json<{ success: boolean; errors: unknown[] }>();
  if (!json.success) {
    throw new Error(`Failed to revoke device ${deviceId}: ${JSON.stringify(json.errors)}`);
  }
}

// Example: revoke all devices for a specific user email
async function revokeUserDevices(email: string): Promise<void> {
  const devices = await allDevices();
  const targets = devices.filter(d => d.user.email === email && !d.revoked);
  await Promise.all(targets.map(d => revokeDevice(d.id)));
  console.log(`Revoked ${targets.length} device(s) for ${email}`);
}
```

---

## 5. API: Query Device Posture Results

After configuring posture checks in the Zero Trust dashboard (OS version, disk encryption,
firewall), read per-device posture results to feed into compliance dashboards.

```typescript
interface PostureResult {
  id: string;
  timestamp: string;
  success: boolean;
  rule: { name: string; id: string };
}

async function getDevicePosture(deviceId: string): Promise<PostureResult[]> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/devices/${deviceId}/posture`,
    { headers: { Authorization: `Bearer ${API_TOKEN}` } }
  );
  const json = await res.json<{ result: PostureResult[]; success: boolean }>();
  if (!json.success) throw new Error('Posture API error');
  return json.result;
}

// Build a compliance report
async function complianceReport() {
  const devices = await allDevices();
  const report = await Promise.all(
    devices.map(async d => ({
      device: d.name,
      user: d.user.email,
      posture: await getDevicePosture(d.id),
    }))
  );
  return report.filter(r => r.posture.some(p => !p.success));
}
```

---

## 6. Terraform-Managed Enrollment Rules

Use the Cloudflare Terraform provider to enforce enrollment policies as code:

```hcl
resource "cloudflare_zero_trust_device_default_profile" "corp" {
  account_id       = var.account_id
  captive_portal   = 180
  disable_auto_fallback = false
  gateway_unique_id    = cloudflare_zero_trust_gateway_settings.main.id

  service_mode_v2 {
    mode = "warp"
  }
}

resource "cloudflare_zero_trust_device_enrollment_permissions" "corp" {
  account_id = var.account_id

  rules {
    name    = "Allow corp email domain"
    action  = "allow"
    precedence = 1
    match   = "identity.email matches \".*@example\\.com\""
  }

  rules {
    name    = "Block all others"
    action  = "block"
    precedence = 2
    match   = "identity.email != \"\""
  }
}
```

---

## Anti-Patterns

- **Storing the API token in client-side MDM profiles.** The token is an admin credential;
  it should only exist in your CI/CD secrets manager or a backend service, never on endpoints.
- **Revoking devices without also terminating IdP sessions.** Revoking the WARP enrollment
  disconnects the tunnel but does not invalidate the IdP SSO session. Combine revocation
  with your IdP's session revocation API.
- **Using account-scoped API tokens for device-level operations.** Create a narrowly scoped
  token with only `Zero Trust: Edit` permissions to limit blast radius.
- **Skipping the `switch_locked` setting for BYOD devices.** Without it, users can disable
  WARP and bypass Gateway DNS filtering.

---

## Gotchas

- MDM profiles are read once at WARP startup; changes do not take effect until the service
  restarts. Push a profile update and restart the service from MDM.
- The `organization` value in MDM config must be your team name (the subdomain of
  `cloudflareaccess.com`), not your account name or zone.
- Device re-enrollment after revocation requires the user to re-authenticate via the IdP.
  There is no silent re-enrollment without user action unless you combine it with a
  Service Auth token configured in the MDM profile.
- Cloudflare's WARP client on iOS and Android requires a per-platform MDM payload; the
  macOS `.mobileconfig` is not cross-platform.
- Posture check results are cached; fresh results may take up to 5 minutes to appear
  after the WARP client reports them.

---

## Verification

```bash
# Confirm API token has the right permissions
curl -s https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/devices?per_page=1 \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '.success, .result[0].name'

# Confirm WARP enrollment on a managed macOS device
/Applications/Cloudflare\ WARP.app/Contents/Resources/warp-cli status
# Expected: "Status update: Connected"
```

---

## Related

- `zero-trust-warp-client-policies.md`
- `cloudflare-zero-trust-warp-to-warp-private-network.md`
- `zero-trust-device-posture.md`
- `cloudflare-terraform-provider-iac.md`
- `warp-connector-site-to-site-zero-trust.md`

---

## Sources

- https://developers.cloudflare.com/cloudflare-one/connections/connect-devices/warp/deployment/mdm-deployment/
- https://developers.cloudflare.com/api/resources/zero_trust/subresources/devices/
- https://developers.cloudflare.com/cloudflare-one/identity/devices/
