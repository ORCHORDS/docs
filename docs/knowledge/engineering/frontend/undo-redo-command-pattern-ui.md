# undo-redo-command-pattern-ui

**Issue:** Users expect Cmd+Z to work in editors, kanban boards, form builders, and canvas tools — but most apps wire undo ad hoc or not at all. Undo has two competing architectures (snapshot-based time travel versus command-pattern inverse operations), and the right choice depends on state size, side effects, and whether other users are editing concurrently. Snapshots are trivial to implement but clobber peers' changes in multiplayer and balloon memory on large documents; command inverses stay surgical but demand that every mutation be modeled as a reversible operation, including API calls. Undo also interacts badly with high-frequency input (drag, resize, typing) and with server-state caches that do not roll back with local state.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Choosing the architecture

1. **Snapshot (memento/temporal) undo for local UI state.** Keep a past/present/future stack of state snapshots; undo pops present into future and restores past. This is what redux-undo implements for Redux and zundo implements for Zustand — zundo attaches a `temporal` object with `undo()`, `redo()`, `clear()`. It is the correct default for editor-local state under a few hundred KB where every mutation is already a state transition.
2. **Command pattern when operations have side effects.** Model each user action as a command object with `do()` and optional `undo()`; the history stores commands, not state. Side effects (API calls, file writes) can be paired with compensating inverse calls (undo = "move item back", not "restore entire document snapshot"). This is the architecture Figma-and-friends style editors converge on, and the classic Redux docs "implementing undo history" essay covers the state variant of it.
3. **Do not use plain full-state snapshots once side effects exist.** Swapping state back to a previous snapshot silently desyncs the server: undo a delete and the server still has the deletion. If mutations hit an API, either the command carries its inverse network call, or undo is paired with explicit re-issue of the affected mutations.
4. **In multiplayer, snapshot undo is wrong.** Replacing state with an old snapshot rolls back other users' concurrent edits. Operation-based undo must reapply the inverse relative to the current document — Liveblocks' multiplayer undo guidance frames it exactly this way: single-user undo is a time machine, multi-user undo reapplies inverse operations. If collaboration is on the roadmap, start with command-based undo even for single-user features.

## Controlling memory and history quality

1. **Partialize what goes into history.** zundo's `partialize` option tracks only undoable slices (the document, the board), never ephemeral state (selection, hover, modal open). Without it every unrelated state change pollutes history and "undo" appears to do nothing.
2. **Cap history with a limit.** zundo's `limit` bounds the stack (e.g. 100 entries); unbounded history in a long editing session is a slow leak that eventually shows up as a memory regression.
3. **Coalesce high-frequency actions into one undo step.** Typing should undo by word or burst, not by character; dragging should undo as one move, not 300 micro-moves. Debounce/batch commits to the history store (commit on pause or on pointerup), or the first Cmd+Z appears to do nothing while it peels back one pixel of a drag. Keep high-frequency transient state out of the undoable store entirely and fold it in at interaction end.
4. **Use equality checks to skip no-op snapshots.** zundo supports an `equality` option so identical states do not stack duplicates; clicking around a UI that does not change undoable state must not grow history.
5. **Group compound operations.** "Paste three items" or "apply template" should be one undo step. With commands, this is a composite command (a list of children executed forward, undone in reverse); with snapshots, commit once after the whole operation settles.

## Wiring undo into the rest of the app

1. **Separate undoable client state from server cache.** The TanStack/Zustand split: server documents live in the query cache; undoable working state lives in the undoable store; on undo, reconcile both — restore the snapshot and re-issue/compensate the network mutations. Treating the query cache as the undo store means undo fights refetches and revalidation.
2. **Drive the keyboard shortcut from one place.** A single global handler for Cmd+Z / Cmd+Shift+Z (and Ctrl+Y as the Windows redo variant) that calls into the history store, with guards to skip when focus is in a native input that has its own undo (text fields should use the browser's built-in per-field undo unless the app implements document-level text history).
3. **Make undo history observable by the UI.** Toolbar buttons should disable when `pastStates.length === 0` / `futureStates.length === 0`; zundo exposes these on the temporal store. Greyed-out undo buttons that still fire are a common bug once undo is wired to multiple stores.
4. **Undo across multiple store slices is the known pain point.** Community experience with zundo (Zustand discussion #1611) is that undo spanning several slices needs one umbrella store or a shared history coordinator — decide the slice topology before adding history middleware, because retrofitting multi-slice undo is a rewrite.
5. **Show what undo did.** After undo, announce the effect (toast: "Undo move") or make the changed region visibly update. Silent undo on a long list where the change scrolled out of view looks like a broken shortcut.
6. **Test redo after undo-then-new-action.** The classic history bug: undo twice, then perform a new action — the future stack must be cleared, or redo resurrects a stale branch over the new state. Every history implementation must pass this sequence test.
