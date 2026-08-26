# windows-mcp-stdio-npx-pitfall

**Issue:** Configuring an MCP stdio server on Windows with `"command": "npx"` (the ubiquitous cross-platform incantation from every README) fails in a large class of MCP hosts: the server never connects, its tools never appear, and host logs show `spawn npx ENOENT`, `spawn EINVAL`, or `CreateProcess error=193`. The cause is that `npx` on Windows is not an executable — it is an `npx.cmd` batch-script shim — and hosts that spawn stdio servers via `child_process.spawn` without `shell: true` cannot execute `.cmd` shims at all (Node has refused since the April 2024 BatBadBut hardening, CVE-2024-27980). The durable fix we shipped in gmail-mcp-connector is to stop launching through npx entirely: resolve the package's real entry script once, then configure the host to invoke `node <absolute-script-path>` directly.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

1. **Server listed but never connects.** The MCP host shows the server entry (or spins on "connecting"), no `mcp__server__*` tools are registered, and after a timeout the host marks it failed — with no obvious error surfaced in the UI.
2. **`spawn npx ENOENT` in host logs.** The host spawned `npx` as a bare name, Windows `CreateProcess` found no `npx.exe` on PATH (only `npx.cmd`), and the spawn failed before the process ever started.
3. **`spawn EINVAL` or `CreateProcess error=193`.** The host DID resolve `npx.cmd` and tried to execute the batch shim directly; Node 18.20+/20.12+ throws `EINVAL` for `.cmd`/`.bat` without `shell: true` (CVE-2024-27980 / BatBadBut hardening), and Windows itself returns error 193 (`ERROR_BAD_EXE_FORMAT`) when a script file is handed to `CreateProcess`.
4. **Host-dependent flakiness.** The same config works in one host and fails in another, because hosts disagree on whether to resolve `.cmd` shims or set `shell: true` — documented across [github/copilot-cli#3576](https://github.com/github/copilot-cli/issues/3576) ("all stdio MCP servers whose command is npx — or any other `.cmd`/`.ps1`/extensionless launcher on PATH — fail to start on Windows"), [JetBrains JUNIE-611](https://you-track.jetbrains.com/projects/JUNIE/issues/JUNIE-611), and [Cline spawn-npx questions on Stack Overflow](https://stackoverflow.com/questions/79586881/spawn-npx-enoent-or-spawn-einval-when-configuring-mcp-server-with-cline-exte).

## Root cause

1. **`npx` is a shim, not an executable.** On Windows, npm installs `npx` as `npx.cmd` (a batch wrapper) plus an extensionless shell script for POSIX environments. Only `.exe` files are directly spawnable by `CreateProcess`; everything else needs `cmd.exe /c` — an extra process layer the host did not ask for.
2. **Node's BatBadBut hardening made it a hard failure.** Before April 2024, `spawn("npx", ...)` sometimes "worked" by accident. After the fix for CVE-2024-27980 (Node 18.20.1/20.12.1+), spawning `.cmd`/`.bat` files without `shell: true` throws `EINVAL` by design — the vulnerability was exactly argument-injection through batch files. Hosts cannot silently paper over this anymore.
3. **`shell: true` is a security hole, so hosts avoid it.** Wrapping the command in `cmd /c npx ...` or spawning with `shell: true` executes the shim but re-parses every argument through the shell, re-opening the BatBadBut injection class. Hosts that refuse it are correct; configs that depend on it are fragile.
4. **Even when the shim runs, stdio semantics can degrade.** The `.cmd` layer inserts `cmd.exe` between host and node: signal handling, child-kill propagation, and clean stdout piping (the JSON-RPC channel!) all traverse an extra process that does not forward them faithfully in every host.

## The fix: bypass npx, invoke node directly

1. **Resolve the real entry script once.** Run the package (`npx -y <package>` or install it), then locate the concrete JS entry — e.g. `node -e "console.log(require.resolve('<package>/dist/index.js'))"` or read `node_modules/<package>/package.json`'s `bin` field. You now have a stable `<absolute>\dist\index.js` path.
2. **Configure the host with `"command": "node"`.** The MCP config becomes `"command": "node", "args": ["C:\\absolute\\path\\to\\dist\\index.js"]` — `node.exe` is a true executable, spawn works in every host with no shim layer, and the stdio JSON-RPC channel is host-to-node with nothing in between. This is what unblocked gmail-mcp-connector on Windows.
3. **Keep the package outside a version-manager-shifting tree.** If node lives under an nvm/fnm/scoop "current" junction, prefer a package location that does not move when you switch Node versions (a fixed app dir or global prefix), or the resolved absolute path goes stale the next day.
4. **Quote paths with spaces.** `C:\Program Files\nodejs\...` contains a space; in JSON configs the backslash-escaped absolute path must stay a single argv entry. A config that silently splits on the space reproduces ENOENT with a different cause.

## Second-class workarounds (and why they lose)

1. **`"command": "npx.cmd"`.** Naming the shim explicitly lets hosts that spawn shims correctly (JetBrains' fix in JUNIE-611) work — but it keeps the `cmd.exe` layer in the stdio chain and does nothing for hosts that hard-refuse `.cmd` spawns.
2. **`cmd /c npx -y <package>`.** The [widely-circulated Windows 11 fix](https://fransiscuss.com/2025/04/22/fix-spawn-npx-enoent-windows11-mcp-server/) — it starts reliably, but every argument is re-interpreted by the shell, and `-y` re-resolution adds seconds of cold-start to every server launch.
3. **Global install + absolute binary path.** `npm i -g` then point the config at the installed CLI — same node-direct spirit, but you now maintain a global install; [nvm/npm layout drift breaks it](https://chanmeng666.medium.com/solution-for-mcp-servers-connection-issues-with-nvm-npm-5529b905e54a).
4. **Doing nothing and blaming the host.** Host behavior genuinely varies, but "works in Claude Desktop, fails in Copilot CLI" is not actionable. The node-direct config is the one form every host accepts because it demands nothing special of the spawner.

## Verification

1. **Manual spawn test first.** Before touching the MCP config, run the exact command from a terminal: `node C:\...\dist\index.js` must start and speak stdio (send it an `initialize` JSON-RPC message on stdin and read the response). If this fails, the problem is the server, not Windows.
2. **Inspector round-trip.** `npx @modelcontextprotocol/inspector node C:\...\dist\index.js` connecting, listing tools, and invoking one proves the transport end-to-end.
3. **Check host logs, not just the UI.** Grep the host's MCP log for `ENOENT|EINVAL|error=193` after the config change; absence of those lines plus tools appearing is the pass condition.
4. **Re-test after Node upgrades.** Switching Node via a version manager is the classic way a working node-direct config breaks — the resolved script path survives, but a globally-installed package under the old version's tree does not.
