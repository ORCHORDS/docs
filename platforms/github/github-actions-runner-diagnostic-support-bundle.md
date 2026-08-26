# GitHub Actions Self-Hosted Runner Diagnostic Support Bundle

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A self-hosted runner registered to your Cloudflare Workers monorepo:
- Stops picking up jobs without error ("queued" state forever in the Actions UI)
- Disconnects mid-job with `Lost connection to GitHub` in the runner log
- Fails to start after an OS update or Docker upgrade
- Produces cryptic `System.Net.Http.HttpRequestException` errors in `_diag/` logs

Before opening a GitHub support ticket or spending hours in log files, collect a
**diagnostic support bundle** — a structured snapshot of runner state, logs, and network
conditions that enables root-cause analysis in minutes rather than hours.

---

## Context

The GitHub Actions runner is an open-source .NET application
(`github.com/actions/runner`). It writes structured logs to:

| Path | Contents |
|------|----------|
| `_diag/Runner_*.log` | Main runner service log (connection, registration, job dispatch) |
| `_diag/Worker_*.log` | Per-job worker process log (step execution, plugin errors) |
| `_diag/pages/` | Internal paging/checkpoint files |
| `_work/_temp/` | Temporary files written by workflow steps (cleaned after job) |

Log rotation: the runner keeps the last **10** `Runner_*.log` and **10** `Worker_*.log` files
by default. Older logs are deleted automatically. Collect logs promptly after an incident.

Runner version, OS, and connectivity details are the most common root causes. GitHub's support
team needs all of them in one bundle.

---

## Manual Bundle Collection (Linux / macOS)

```bash
#!/usr/bin/env bash
# collect-runner-diag.sh
# Run as the user that owns the runner process

set -euo pipefail

RUNNER_ROOT="${RUNNER_ROOT:-/opt/actions-runner}"
BUNDLE_DIR="${TMPDIR:-/tmp}/runner-diag-$(date +%Y%m%dT%H%M%S)"
mkdir -p "$BUNDLE_DIR"

echo "[1/6] Runner version and registration"
cat "$RUNNER_ROOT/.runner"        > "$BUNDLE_DIR/runner-config.json"  2>/dev/null || true
cat "$RUNNER_ROOT/.credentials"   > "$BUNDLE_DIR/runner-creds.json"   2>/dev/null || true
"$RUNNER_ROOT/bin/Runner.Listener" --version                           \
  > "$BUNDLE_DIR/runner-version.txt" 2>&1 || true

echo "[2/6] OS and environment"
{
  uname -a
  cat /etc/os-release 2>/dev/null || sw_vers 2>/dev/null || true
  echo "--- PATH ---"
  echo "$PATH"
  echo "--- ENV (redacted) ---"
  env | grep -v -E 'TOKEN|SECRET|PASSWORD|KEY|PAT' | sort
} > "$BUNDLE_DIR/environment.txt"

echo "[3/6] Diag logs (last 5 Runner and last 5 Worker logs)"
mkdir -p "$BUNDLE_DIR/diag"
ls -t "$RUNNER_ROOT/_diag/Runner_"*.log 2>/dev/null | head -5 | \
  xargs -I{} cp {} "$BUNDLE_DIR/diag/" || true
ls -t "$RUNNER_ROOT/_diag/Worker_"*.log 2>/dev/null | head -5 | \
  xargs -I{} cp {} "$BUNDLE_DIR/diag/" || true

echo "[4/6] Network connectivity"
{
  echo "=== DNS resolution ==="
  nslookup api.github.com       || true
  nslookup pipelines.actions.githubusercontent.com || true
  echo "=== HTTPS reachability ==="
  curl -sv --max-time 10 https://api.github.com/zen 2>&1 | \
    grep -E '^[<>*]|TLS|SSL|error|connected' || true
  echo "=== Proxy settings ==="
  echo "HTTP_PROXY=${HTTP_PROXY:-unset}"
  echo "HTTPS_PROXY=${HTTPS_PROXY:-unset}"
  echo "NO_PROXY=${NO_PROXY:-unset}"
  echo "=== Open connections to GitHub ==="
  ss -tn 2>/dev/null | grep ':443' || netstat -tn 2>/dev/null | grep ':443' || true
} > "$BUNDLE_DIR/network.txt"

echo "[5/6] Process and service status"
{
  echo "=== Runner processes ==="
  pgrep -la Runner || true
  echo "=== Systemd service (if applicable) ==="
  systemctl status actions.runner.* 2>/dev/null || true
  echo "=== Docker (if applicable) ==="
  docker info 2>/dev/null || true
} > "$BUNDLE_DIR/processes.txt"

echo "[6/6] Disk and file descriptors"
{
  df -h "$RUNNER_ROOT"
  echo "--- inode usage ---"
  df -i "$RUNNER_ROOT"
  echo "--- open file descriptors ---"
  ls /proc/$(pgrep -x Runner.Listener | head -1)/fd 2>/dev/null | wc -l || true
} > "$BUNDLE_DIR/disk.txt"

# Create archive
BUNDLE_ARCHIVE="${BUNDLE_DIR}.tar.gz"
tar -czf "$BUNDLE_ARCHIVE" -C "$(dirname "$BUNDLE_DIR")" "$(basename "$BUNDLE_DIR")"
rm -rf "$BUNDLE_DIR"

echo "Bundle created: $BUNDLE_ARCHIVE"
echo "Safe to share: network.txt redacts tokens. Verify before attaching to support ticket."
```

---

## Windows Bundle Collection

```powershell
# collect-runner-diag.ps1
$RunnerRoot = $env:RUNNER_ROOT ?? "C:\actions-runner"
$BundleDir  = "$env:TEMP\runner-diag-$(Get-Date -Format 'yyyyMMddTHHmmss')"
New-Item -ItemType Directory -Path $BundleDir | Out-Null

# Runner version
& "$RunnerRoot\bin\Runner.Listener.exe" --version > "$BundleDir\runner-version.txt" 2>&1

# Diag logs
$DiagDest = "$BundleDir\diag"
New-Item -ItemType Directory -Path $DiagDest | Out-Null
Get-ChildItem "$RunnerRoot\_diag\Runner_*.log" | Sort-Object LastWriteTime -Descending |
  Select-Object -First 5 | Copy-Item -Destination $DiagDest
Get-ChildItem "$RunnerRoot\_diag\Worker_*.log" | Sort-Object LastWriteTime -Descending |
  Select-Object -First 5 | Copy-Item -Destination $DiagDest

# Network
$NetworkLog = "$BundleDir\network.txt"
"=== DNS ===" | Out-File $NetworkLog
Resolve-DnsName api.github.com | Out-File $NetworkLog -Append
"=== HTTPS ===" | Out-File $NetworkLog -Append
Invoke-WebRequest https://api.github.com/zen -UseBasicParsing 2>&1 |
  Select-Object StatusCode, Content | Out-File $NetworkLog -Append

# Archive
Compress-Archive -Path $BundleDir -DestinationPath "$BundleDir.zip"
Remove-Item -Recurse -Force $BundleDir
Write-Host "Bundle: $BundleDir.zip"
```

---

## Automated Bundle on Runner Failure (GitHub Actions)

Upload a diagnostic bundle as an Actions artifact whenever a self-hosted runner job fails:

```yaml
# .github/workflows/ci.yml  (excerpt)
jobs:
  build:
    runs-on: [self-hosted, linux, workers]
    timeout-minutes: 30

    steps:
      - uses: actions/checkout@v4

      - name: Build
        id: build
        run: pnpm run build

      - name: Collect runner diagnostics on failure
        if: failure()
        run: |
          BUNDLE_DIR="$RUNNER_TEMP/diag-$(date +%s)"
          mkdir -p "$BUNDLE_DIR"

          # Logs written during this job (Worker logs are still live)
          cp "$RUNNER_ROOT/_diag/Worker_"*.log "$BUNDLE_DIR/" 2>/dev/null || true

          # Snapshot network state
          {
            echo "=== DNS ==="
            nslookup api.github.com
            echo "=== Open TLS connections ==="
            ss -tn | grep ':443' || true
          } >> "$BUNDLE_DIR/network-at-failure.txt"

          # System resources
          {
            echo "=== Memory ==="
            free -h
            echo "=== Disk ==="
            df -h "$RUNNER_ROOT"
            echo "=== Load ==="
            uptime
          } >> "$BUNDLE_DIR/resources-at-failure.txt"

          tar -czf "$RUNNER_TEMP/runner-diag.tar.gz" -C "$RUNNER_TEMP" \
            "$(basename "$BUNDLE_DIR")"
        env:
          RUNNER_ROOT: ${{ runner.tool_cache }}/../../../..

      - name: Upload diagnostic bundle
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: runner-diag-${{ github.run_id }}-${{ github.run_attempt }}
          path: ${{ runner.temp }}/runner-diag.tar.gz
          retention-days: 7
```

---

## Interpreting Common Log Patterns

```
# Pattern: runner not picking up jobs
Runner_20260822-090100.log:
  [2026-08-22 09:01:00Z INFO  GitHubActionsService] ...
  FATAL: Unable to connect to the server

Diagnosis: Check HTTPS proxy settings. The runner uses HTTPS to long-poll
GitHub's Actions service. A transparent proxy intercepting TLS without
a trusted certificate will break the connection silently.

# Pattern: job stalls at "Set up job"
Worker_20260822-090100.log:
  Downloading action 'actions/checkout@v4'
  FATAL: The SSL connection could not be established

Diagnosis: The runner's OS certificate store is out of date, or the
corporate proxy is MITMing HTTPS. Run:
  update-ca-certificates  (Debian/Ubuntu)
  sudo security add-trusted-cert -d ...  (macOS)

# Pattern: "Lost connection" mid-job
Runner_20260822-091530.log:
  [ERROR] System.Net.Http.HttpRequestException: Response status code does
  not indicate success: 403 (Forbidden).

Diagnosis: Runner registration token expired. Re-register the runner:
  ./config.sh remove --token <REMOVE_TOKEN>
  ./config.sh --url https://github.com/acme-corp/repo \
              --token <NEW_REGISTRATION_TOKEN>
```

---

## Runner Diagnostics via GitHub CLI

```bash
# Check which runners are online / offline for a repo
gh api repos/acme-corp/api-gateway/actions/runners \
  --jq '.runners[] | {name, status, busy, labels: [.labels[].name]}'

# Check which runners belong to a runner group
gh api orgs/acme-corp/actions/runner-groups \
  --jq '.runner_groups[] | {id, name, visibility}'

# Trigger a test workflow to isolate runner issues
gh workflow run ci.yml --ref main \
  --field "runner=self-hosted"
```

---

## Anti-patterns

- **Sharing raw `_diag/*.log` files externally without review** — diag logs may contain
  environment variable values that were echoed by a step, including partial secret values.
  Review or redact before attaching to a ticket.

- **Waiting 24 hours to collect logs** — the runner rotates and deletes logs automatically.
  Collect within 1 hour of an incident.

- **Restarting the runner service before collecting diagnostics** — a restart clears the
  in-memory state and closes the current `Runner_*.log` file, making correlation harder.
  Collect first, restart after.

- **Diagnosing in production under load** — deploy a spare "diagnostic" runner with debug
  logging enabled (`ACTIONS_RUNNER_DEBUG=true`) for incident reproduction rather than
  enabling verbose logging on production runners.

---

## Gotchas

- **`RUNNER_ROOT` is not a standard env var** — the runner does not export its own root path.
  Derive it from `GITHUB_ACTION_PATH` inside a job (`dirname "$(dirname "$GITHUB_ACTION_PATH")"`)
  or hard-code the path in your support script.

- **Docker-in-Docker runner logs** — if the runner itself runs inside a container, `_diag/`
  logs are inside the container filesystem. Mount a host volume or use `docker cp` to extract.

- **Runner version mismatch** — GitHub may retire old runner versions and stop dispatching
  jobs to them silently. Always check `/repos/{owner}/{repo}/actions/runners` for the
  `version` field and compare against the latest release.

- **`ACTIONS_RUNNER_DEBUG` and `ACTIONS_STEP_DEBUG`** — setting these to `true` (as repository
  secrets or environment variables) enables verbose logging in the Worker logs but does not
  increase Runner log verbosity. They are different log streams.

---

## Verification

```bash
# Confirm runner is registered and online
gh api repos/acme-corp/api-gateway/actions/runners \
  --jq '.runners[] | select(.name == "prod-runner-01") | {status, busy}'
# Expected: {"status": "online", "busy": false}

# Confirm the bundle captures the right time range
tar -tzf runner-diag.tar.gz | grep '\.log'
# Should list Runner_YYYYMMDD-*.log files from the incident window
```

---

## Related

- `github-actions-self-hosted-runners-2026.md` — self-hosted runner setup overview
- `github-actions-ephemeral-jit-runner-registration.md` — JIT registration
- `github-actions-runner-version-update-enforcement.md` — runner version governance
- `self-hosted-runner-job-hooks-for-cleanup-and-telemetry.md` — job hooks for observability
- `github-self-hosted-runner-proxy-startup-contract.md` — proxy configuration

---

## Sources

- https://docs.github.com/en/actions/monitoring-and-troubleshooting-workflows/troubleshooting-self-hosted-runners
- https://github.com/actions/runner/blob/main/docs/contribute.md
- https://docs.github.com/en/rest/actions/self-hosted-runners
- https://docs.github.com/en/actions/security-guides/encrypted-secrets#naming-your-secrets (ACTIONS_RUNNER_DEBUG)
