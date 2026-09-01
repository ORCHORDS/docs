# SSH Config Include Directives for Multiple Hosts

A single flat `~/.ssh/config` grows until it hurts: hundreds of host stanzas, credentials mixed across personal and work machines, laptop versus CI needing different settings, and every edit risking the one file every connection depends on. OpenSSH's `Include` directive decomposes the config into composable files — per-employer, per-environment, per-tool — with defined first-match-wins semantics. Used deliberately, includes give you scoped organization, safe automation (tools write their own included file instead of appending to yours), and a clean audit surface. Used sloppily, they give you settings from five files you forgot existed. This article covers include mechanics, match-order semantics, layered layouts, and operational discipline.

## Scope

This article addresses the OpenSSH client `Include` directive (and the config processing model it participates in): include paths and globbing, per-user versus system config layers, first-obtained-value semantics, conditional blocks (`Match`), and patterns for managing many hosts across work/personal/tooling boundaries. It does not cover SSH server configuration, agent forwarding security policy broadly, or jump-host topology design beyond configuration structure.

## Workflow or implementation guidance

OpenSSH client configuration is processed in a fixed order: command-line options, then user config (`~/.ssh/config`), then system config (`/etc/ssh/ssh_config`) — with the rule that for most options, **the first value obtained wins**, so processing order is semantic. `Include` pulls other files inline at the point of the directive, and the included files are processed with the same first-wins rule. Two consequences follow:

1. **Order is policy.** A `Host` block in an included file processed earlier overrides the same option in a later block, even if the later block's pattern also matches. Layouts must therefore place the most specific files first: `Include ~/.ssh/config.d/*.conf` placed *above* your generic stanzas lets per-host files win.
2. **Glob expansion is deterministic.** `Include` supports glob patterns expanded lexicographically — `config.d/*.conf` includes `a-…` before `b-…`; rely on filename prefixes (`10-personal.conf`, `20-work.conf`) to control precedence explicitly rather than hoping.

A robust layered layout:

```
~/.ssh/config                  # orchestrator: Includes + cross-cutting defaults
~/.ssh/config.d/
  10-personal.conf             # personal hosts
  20-work-legacy.conf          # acquired company; distinct bastion patterns
  30-work-current.conf
  40-auto-*.conf               # tool-managed (cloud CLIs, IDEs) — lowest priority by naming
```

The orchestrator file stays small:

```
Include ~/.ssh/config.d/*.conf

Host *
  AddKeysToAgent yes
  IdentitiesOnly yes
  ServerAliveInterval 60
```

Practical patterns that earn their keep:

- **Per-environment files with shared identity blocks.** Work stanzas repeat `User`, `ProxyJump`, and identity; group them per file and keep one `Host *` defaults block in the orchestrator only. Multiple `Host *` blocks across files are legal but first-wins makes later ones mostly dead settings — a confusion generator; keep exactly one.
- **`Match` blocks for context-sensitive settings.** `Match host "*.internal.corp" user "me"` can apply work settings only when both conditions hold — sharper than `Host` patterns alone and self-documenting. `Match originalhost` distinguishes the jump target from the final destination when chaining.
- **Tool-managed includes.** Tools that write SSH config (some cloud CLIs provisioning ephemeral hosts, IDE remote extensions) should never edit your hand-written files. Give them their own included file or a dedicated directory they own entirely (`config.d/90-generated.conf` or a separate tree), and treat its contents as disposable. This is the single biggest reliability win of includes: automation writes its file; your files never suffer append-corruption.
- **Identity hygiene.** `IdentitiesOnly yes` in defaults plus explicit `IdentityFile` per host family prevents the agent from offering every key to every server (which leaks which keys you hold and can get you disconnected for too-many-auth-failures when the agent tries keys before the server wants the right one). Scope identities in the per-scope files, never one global kitchen-sink identity list.
- **Cannonicalization for aliased hosts.** `CanonicalizeHostname` + `Host` alias blocks let short names (`ssh staging`) resolve through one canonical pattern — keep the aliases and the real-name blocks in the same included file so the mapping is visible in one place.
- **Readability gates.** `ssh -G <host>` dumps the *effective* merged config for a host — the definitive answer to "which value is winning and from where". `ssh -F /dev/null` bypasses user config for testing defaults. Make `-G` part of debugging habit; it turns include-order mysteries into one-command answers.

A worked example: an engineer with personal servers, two employers' infrastructures, and an IDE writing remote-host entries migrates a 400-line flat config: orchestrator gains the `Include`; hosts split into `10-personal`, `20-acme`, `30-globex`, each carrying its own `ProxyJump`, `User`, and `IdentityFile` scoping; the IDE is pointed at `config.d/95-ide.conf` it may own. When the IDE misbehaves, its file is deleted and regenerated without touching human-managed stanzas; when the acme contract ends, one file is removed and one include-glob still works — decommissioning is file deletion, not surgical editing.

## Controls

- One `Host *` defaults block, in the orchestrator file, after includes — enforced by review; a second `Host *` anywhere is a defect.
- Filename-prefix ordering (`NN-name.conf`) for all files in included directories; document the numbering scheme in the orchestrator's comment header.
- Tool-written config confined to tool-owned files/directories; audit with a periodic diff of human-managed files (they should only change in reviewed commits if config is repo-managed via dotfiles).
- Verify effective configuration with `ssh -G <host>` during onboarding and incident triage; store the expected `-G` output for critical bastions in the runbook so regressions are diffable.
- Never commit private keys alongside split configs in dotfiles repos — includes make the config tree tempting to version; version the `.conf` files, never the `keys/` directory.

## Validation evidence

- The `Include` directive, its glob processing and lexicographic expansion, the first-value-obtained precedence rule, `Match` conditionals (including `originalhost`), `CanonicalizeHostname`, and `-G`/`-F` behavior are specified in the official OpenSSH client configuration manual page (ssh_config, published at man.openbsd.org) maintained by the OpenSSH project.
- The layered user/system configuration model and processing order are documented in the same manual page's Files section.
- A reproducible experiment: create `config.d/10-a.conf` setting `ServerAliveInterval 30` for `Host *`, and `config.d/20-b.conf` setting it to `99`; run `ssh -G example.com | grep serveraliveinterval` — output shows 30, the first value; swap the numeric prefixes and it shows 99 — precedence demonstrated in two commands.

## Failure modes and correction

- **Forgotten files overriding intent.** Symptom: a setting no one remembers setting wins. Correct by `ssh -G` triage and the numbering-scheme convention; delete dead files aggressively.
- **Second `Host *` block silently dead.** Symptom: someone's "override" does nothing. Correct by the one-defaults-block rule.
- **Tool appends corrupting hand-written config.** Symptom: broken YAML-adjacent stanza kills all SSH until repaired. Correct by tool-owned include files.
- **Over-broad identity offering.** Symptom: `Too many authentication failures` or key-presence leaks. Correct with `IdentitiesOnly` plus scoped `IdentityFile` per file.
- **Include path portability.** Symptom: config copied between machines misses files (`~/` expansion works; relative paths resolve relative to the including file's directory — but absolute personal paths break on other usernames). Correct by `~/`-rooted paths only.

## Limitations

- First-wins semantics mean later files cannot override earlier ones for most options — include layout is a one-way precedence design, and "temporarily override" is not what includes give you (use command-line `-o` for that).
- Debugging merged behavior requires `-G` or `-v`; there is no built-in "show which file set this option" beyond verbose tracing.
- Windows OpenSSH config layering differs slightly in default locations; cross-platform dotfiles need per-OS handling.
- System-managed environments (ephemeral CI) often bypass user config entirely; include-based organization is a workstation-scale pattern.

## Canonical sources

- OpenBSD (OpenSSH project), ssh_config(5) Manual Page — Include, Match, precedence, options: https://man.openbsd.org/ssh_config
- OpenBSD (OpenSSH project), ssh(1) Manual Page — client configuration resolution and -F/-G behavior: https://man.openbsd.org/ssh
