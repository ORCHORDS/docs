# zellij-terminal-workspace

**Issue:** tmux is ubiquitous but famously undiscoverable — prefix keybindings must be memorized, per-project layouts require scripting, and sharing sessions is bolted on. Zellij (Rust, WASM plugins) solves the same persistent-session problem with sane defaults, an on-screen hint bar, KDL layout files that act as per-project automation, and first-class floating panes. This article covers the core concepts, layout-driven workflows, session management, and customization for teams evaluating or adopting Zellij alongside (or instead of) tmux.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Core concepts vs tmux

1. **Discoverable by default.** Zellij renders a bottom hint bar showing the keys available in the current mode, so a new team member can be productive in minutes without a cheat sheet — the number one difference from tmux's memorize-the-prefix model.
2. **Modes instead of a single prefix.** Keys are grouped into modes — Normal (default), Locked (pass everything through, like tmux's prefix-off), Pane, Tab, Resize, Move, Search, Session, and Tmux — each mode has its own bindings, which is why Zellij can offer many shortcuts without prefix gymnastics.
3. **Floating panes.** Any pane can be toggled to float above the tiled layout (`Ctrl+p` then `w` in default bindings), moved and resized like a window — perfect for a scratch shell or a log tail you only sometimes want visible, something tmux needs popups (newer tmux only) or workarounds to approximate.
4. **Pane and tab primitives match tmux's.** Tabs equal tmux windows, panes equal tmux panes with split_direction support, and panes can be named and focused by name — muscle memory for "split vertically, new tab" transfers directly, only the keys differ.
5. **Copy mode is built in.** Enter copy mode from the pane menu, scroll and select with vim-like or emacs-like keys, and the selection goes to the system clipboard (configurable) — no copy-mode pipeline configuration needed, which is a common tmux pain point on macOS and Windows.

## Layouts as per-project automation

1. **KDL layout files define a whole workspace.** A layout declares tabs, pane splits (direction and proportion), commands to auto-run in each pane, and the starting `cwd` — committing one `dev.kdl` per repo turns "set up my dev environment" into `zellij --layout dev.kdl`.
2. **Every pane can auto-start a command.** Give a pane `"pnpm dev"`, another `"pnpm test --watch"`, another `"docker compose up"` — the layout restores not just geometry but the running processes, unlike tmux scripts that must `send-keys` and hope.
3. **Set a default layout per directory.** `zellij --layout` flags, a `default_layout` in config, or layout templates let `zellij` opened at the repo root bring up the project's canonical pane arrangement; teams standardize on a `layouts/` folder in the repo.
4. **Layout templates parameterize session creation.** Templates inject the session name (and support `+s`-style argument substitution) into pane titles and commands, so one generic "services" template can spin up differently named sessions per stack while keeping commands DRY.
5. **Nested `parts` express split trees.** Layouts nest `pane` blocks with `split_direction` to describe arbitrarily complex arrangements once, instead of hand-splitting every time — the layout file doubles as living documentation of the team's dev topology.

## Session management

1. **Attach, list, delete from the CLI.** `zellij attach <name>`, `zellij list-sessions`, `zellij delete-session <name>`, and `zellij kill-all-sessions` cover day-to-day workflow; `zellij --session <name> --layout <layout>` creates a named session with the layout in one shot.
2. **Sessions survive disconnects like tmux.** Detaching (session mode or terminal close) leaves processes running; re-attaching restores panes — the core multiplexer value, unchanged, which means SSH-drop recovery works identically for remote dev boxes.
3. **Session resurrection after restart.** With the built-in session resurrection functionality enabled in options, Zellij can restore pane layouts (and optionally re-run commands) after a machine or Zellij restart — pair it with `auto_exit`/cleanup options to avoid stale-session clutter.
4. **Rename sessions to match the task.** Renaming a session (session mode) so it reflects the branch or incident (`fix-auth-leak`, `refactor-router`) makes `zellij list-sessions` a de facto task list across the week.
5. **The welcome screen is a launcher.** A fresh `zellij` with no session opens a layout-picker/welcome screen; disabling it via config (`layout` set, or `--layout` habit) gives tmux-style immediacy for users who always want a specific environment.

## Customization and plugins

1. **Config lives in KDL.** `zellij setup --dump-config > ~/.config/zellij/config.kdl` gives a fully commented starting file: themes, default mode, pane frames, copy behavior, on-screen font size, and mouse support are all options — the generated file doubles as reference documentation.
2. **Keybindings are remappable per mode.** Because bindings are mode-scoped, converting a tmux power user is mostly a keybinding file: Zellij even ships a tmux-style keybinding example, so `Ctrl-b`-muscle-memory users can keep their hands.
3. **Themes are declarative.** Theme blocks (with popular presets like Catppuccin trivially pasted in) control every UI surface including the hint bar; `theme` can be switched per-OS-appearance (dark/light) — no status-line scripting like tmux.
4. **WASM plugin system.** Plugins are sandboxed WebAssembly modules compiled from Rust that can render panes, subscribe to events, and run commands — the architecture that built the built-in tab-bar and status plugins, and the basis for community tooling.
5. **Ecosystem plugins worth knowing.** `zellij-sessionizer` (fzf-based project/session jumping), `zellij-forgot` (show a keybinding cheat sheet), and various harpoon-style jump plugins cover the most-missed tmux workflows; install via the documented plugin-alias mechanism in config.kdl.
