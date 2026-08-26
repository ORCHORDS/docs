# ssh-config-mastery

**Issue:** Every host interaction pays a full TCP + key-exchange + auth handshake; hop-and-bastion access is a paste from a wiki page; deploy scripts and loops are 10x slower than they should be; and credentials/config live in a dozen aliases across tools. `~/.ssh/config` is a declarative file that fixes all of it, and almost nobody reads its manual past `HostName`.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The foundation: aliases and first-match-wins

1. **Define host aliases instead of typing full coordinates.** `Host prod` + `HostName 203.0.113.10` + `User deploy` + `Port 2222` + `IdentityFile ~/.ssh/prod_ed25519` turns `ssh -i ~/.ssh/prod_ed25519 -p 2222 deploy@203.0.113.10` into `ssh prod` — and every tool that shells out to ssh (scp, rsync, ansible, git+ssh, tailscale-style overlays) inherits it for free.
2. **Ordering is first-match-wins, so specific blocks go first.** ssh applies the *first* occurrence of each keyword per host, not the last. Put narrow patterns (`Host prod-eu-*`) above broad ones (`Host *`), and use `Host prod-* !prod-eu-*` negations carefully — the mismatched-ordering bug looks like "my config is being ignored".
3. **Preview the effective config with `ssh -G <alias>`.** `-G` prints every resolved option (hostname, user, port, identity files, proxy settings) without connecting — the fastest way to debug why an alias picked the wrong key or port.
4. **Use `Host *` as your defaults block.** Sensible globals: `ServerAliveInterval 30` + `ServerAliveCountMax 3` to kill dead connections, `Compression yes` for high-latency hops, and `AddKeysToAgent yes` so passphrase keys entered once per boot persist in the agent.
5. **Prefer `IdentitiesOnly yes` with an explicit `IdentityFile`.** Without it, ssh offers every key in your agent in order; servers that see too many invalid attempts (MaxAuthTries) can drop you before reaching the right key — the classic "works in a fresh terminal, fails in my long-running one" mystery.

## Multiplexing: one connection, many sessions

1. **Turn on `ControlMaster auto` with a `ControlPath` and `ControlPersist`.** Example: `ControlMaster auto`, `ControlPath ~/.ssh/sockets/%r@%h-%p`, `ControlPersist 10m`. The first session authenticates; every subsequent `ssh`, `scp`, and `rsync` to the same target multiplexes over the existing TCP connection with zero handshake.
2. **Create the socket directory.** ssh will not mkdir `~/.ssh/sockets` for you; a missing directory silently disables multiplexing and you are back to full handshakes without any error. `mkdir -p ~/.ssh/sockets && chmod 700 ~/.ssh` is part of the setup, not an option.
3. **Measure it where it matters: loops and bastions.** Repeated scripted connections (deploy loops, ansible fan-out, rsync batches) drop from seconds each to milliseconds; jump-host setups report connection times falling from ~20s to ~2-3s once the master exists. This is the single biggest ssh-config win for CI and automation.
4. **Manage masters explicitly.** `ssh -O check prod` reports whether a master is alive, `ssh -O exit prod` tears it down cleanly (do this in scripts that must not leak sockets), and a wedged master after a network change is fixed by removing the socket file. `ControlPersist 10m` (or `4h` on laptops) trades connection reuse against stale-connection cleanup.
5. **Do not multiplex in hostile parallelism.** Tens of concurrent long-running sessions over one master share one TCP stream — a saturated link stalls all of them. For heavy parallel fan-out (ansible with many forks), keep multiplexing for control connections and let big transfers open their own channels.

## Jump hosts: ProxyJump over everything else

1. **Use `ProxyJump` (`-J`), not legacy `ProxyCommand nc`.** `ssh -J bastion internal.host` does the modern equivalent of the old netcat pipe with proper host-key and auth handling. In config: `Host internal` / `HostName 10.0.0.5` / `ProxyJump bastion` — and `bastion` can itself be another alias with its own settings.
2. **Chain hops with commas.** `-J hop1,hop2,target` routes through multiple jumps; in config, `ProxyJump user@hop1:2222,hop2` works the same way. Keep the chain in the alias so nobody re-derives it from a wiki.
3. **Multiplex the bastion leg too.** Combine `ProxyJump bastion` with a `ControlMaster` block on the bastion host definition: the expensive WAN+auth hop is paid once, and each new internal session only builds the cheap bastion-to-target leg. The two features compose — the master carries proxied connections.
4. **Keep `ProxyCommand` for the exotic cases only.** When the "jump" is not ssh at all — `openssl s_client`, `docker exec -i`, a kubectl port-forward, or a socat UDP bridge — `ProxyCommand` remains the escape hatch. The OpenSSH cookbook documents these patterns; just do not hand-roll netcat when `-J` exists.
5. **Forward agent or keys deliberately.** For jump hosts, prefer `ForwardAgent no` (the bastion needs no identities) and let the *target* auth happen end-to-end — ProxyJump tunnels the target's ssh protocol through the jump untouched, which is exactly why it is safer than agent-forwarding through a shared bastion.

## Modular config, conditions, and hygiene

1. **Split with `Include`.** `Include ~/.ssh/config.d/*` and `Include ~/.ssh/work` keep personal, work, and per-project hosts in separate files — the work file can even be deployed by your dotfiles manager, and `Include` directives are processed inline so first-match-wins still applies across files in include order.
2. **Use `Match` for conditional config.** `Match host *.corp.example.com` sets VPN-only options; `Match originalhost prod-* user root` narrows further; `Match exec "check-vpn.sh"` gates settings on a script's exit status (are we on the corp network?). `Match final` blocks apply after canonicalization, which matters once you combine it with `CanonicalizeHostname`.
3. **Harden defaults in the `Host *` block.** `HashKnownHosts yes` keeps known_hosts from becoming a map of every host you touched; `PasswordAuthentication no` and `KbdInteractiveAuthentication no` on keys-only targets stop you fat-fingering into password auth; `ForwardX11 no` by default, opting in per host.
4. **Move to hardware/FIDO2-backed keys for long-lived access.** `ssh-keygen -t ed25519-sk` (and `ed25519-sk` resident keys on YubiKeys) makes the private key non-extractable; pair with `IdentitiesOnly yes` and per-host `IdentityFile` entries. Passkey-style ssh workflows are maturing in current OpenSSH, but the portable baseline is still the sk key.
5. **Test the config like code.** `ssh -G` per alias in a smoke script catches ordering and typo regressions; `ssh -O check` after first connect verifies multiplexing actually engaged. A broken `~/.ssh/config` fails closed for every tool at once, so a ten-second check beats a monday of mystery.

## Related

- dotfiles-management-chezmoi-stow (how the config file itself gets distributed)
- tmux-configuration (the other "works on every box" file)
