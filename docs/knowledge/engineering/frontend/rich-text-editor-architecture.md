# rich-text-editor-architecture

**Issue:** Rich text editing is one of the hardest problems shipped to browsers: contenteditable is inconsistent across engines (selection, IME composition, undo, clipboard all behave differently), and product requirements — custom node types, real-time collaboration, mentions, embedded widgets, versioned persistence — pile a document model, a schema, a transaction system, and a serialization format on top. The 2025-2026 landscape has consolidated around three foundations: ProseMirror (battle-tested toolkit, collaboration-first design via transactions and Yjs), TipTap (a headless, DX-focused layer over ProseMirror that the community and comparisons like Liveblocks' and PkgPulse' rate as the best default for CMS/docs products), and Lexical (Meta's React-first, performance-focused rebuild, more low-level, with collaboration requiring your own wiring). Choosing an architecture is a five-year commitment; migrating editors is notoriously expensive because documents outlive code.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Landscape and Selection

1. **ProseMirror for maximum control and collaboration.** ProseMirror models documents as an immutable tree with a strict schema; every change is a transaction, which is exactly the property collaborative editing (Yjs sync) is built on. The ProseMirror forum's own comparison notes its strength is that collaboration is designed into the transaction model rather than bolted on. Cost: the steepest learning curve and the most code for the same result.

2. **TipTap as the pragmatic default.** TipTap is a deliberately shallow abstraction over ProseMirror — headless (bring your own UI in any framework), with modern docs and first-class Yjs collaboration extensions. Community consensus (r/reactjs Lexical-vs-TipTap threads) and the 2025-2026 comparisons converge on it for CMS, docs, and collaborative authoring: most of ProseMirror's power with a fraction of the setup. Watch licensing: some advanced extensions are paid.

3. **Lexical for React-centric, performance-sensitive editors.** Lexical (Meta) is a from-scratch contenteditable replacement: fine-grained updates, a small core, React bindings as the primary API. Comparisons (Medium's Tiptap-vs-Lexical, Liveblocks' framework guide) consistently describe it as more low-level — more control, more wiring. Lexical does not handle collaboration itself; you integrate Yjs through its bindings, which is real integration work.

4. **Slate/Quill only with strong reason.** Slate (React, flexible but historically churny) and Quill (simple, older model, Quill 2 addressing the maintenance gap) remain viable for basic editors, but the 2026 roundups position them behind the three above for new, long-lived products.

5. **Decide collaboration requirements first.** Real-time multi-user editing is the requirement that constrains everything else: it pushes you toward ProseMirror-family (Yjs) or Lexical-with-Yjs-binding, rules out naive HTML-in-a-textarea persistence, and forces conflict-free document models (CRDT-friendly) from day one.

## Document Model Architecture

1. **The editor owns a document tree, not HTML.** All three foundations parse HTML into a typed node tree (doc → paragraph → text with marks; custom nodes like mention, image-embed, code-block). The tree, constrained by a schema, is the source of truth; HTML/DOM is just a rendering and serialization target. Treating the DOM as the model is the original sin that contenteditable-raw editors never recover from.

2. **Define a strict schema and reject invalid content.** The schema declares allowed nodes, their attributes, and nesting rules (what can be inside what). Paste from Word and drag-in of arbitrary HTML must be normalized through the schema — this is how you avoid unstyled spans, broken nesting, and XSS vectors via pasted markup. Normalize on ingest, never trust clipboard input.

3. **Model custom features as first-class nodes and marks.** A mention is a node with an id attribute and an inline atomic render, not bolded text; an upload placeholder is a node that transitions to image-embed when the URL arrives. Modeling features as schema elements gives you selection, undo, copy-paste, and collaboration for free; modeling them as DOM hacks gives you bugs in exactly those four areas.

4. **Never mutate state outside transactions.** Every programmatic change (toolbar actions, AI insertions,mention insertion) goes through the editor's transaction/command API so undo history, collaborative sync, and listeners stay consistent. Direct DOM manipulation inside the editable region desyncs the model — the canonical unfixable-bug generator.

## Framework and State Integration

1. **Keep the editor out of your component tree's re-renders.** The editor instance and its document state must not live as React/Vue state that re-renders on every keystroke. Create the instance once (Lexical's composer, TipTap's useEditor with stable deps), read document state through event-driven subscriptions (selection change, transaction, update listeners), and write through commands. The React compiler/memoization rules apply: unstable props into the editor wrapper cause full editor remounts and caret loss.

2. **Mirror only derived UI state upward.** Word counts, dirty flags, and save-state can flow to app state, but serialize-on-every-keystroke is wrong: debounce persistence serialization (300-500 ms idle), and serialize to JSON (the model's native format), not HTML, when the document is the durable artifact.

3. **Isolate toolbar and menus from the editor.** Toolbars should be headless consumers of editor commands and active-state queries, rendered outside the editable region, so they re-render independently of typing. This is also what makes the same toolbar work across frameworks and keeps keyboard interaction (bold via Ctrl+B without focus loss) correct.

## Collaborative Editing Foundations

1. **Adopt Yjs (Y.CRDT) as the sync backbone.** Yjs is the de facto CRDT for text editing, with mature bindings: y-prosemirror (used under TipTap Collaboration and by many ProseMirror apps) and yjs bindings for Lexical. The editor's transactions map to CRDT operations; offline edits merge without central coordination. The Hacker News consensus that TipTap + ProseMirror + Yjs is "insanely good" reflects how solved this stack is.

2. **Persist the CRDT document, not just JSON.** For collaborative documents, store the Yjs update stream (or merged state) server-side as the canonical artifact, with derived JSON/HTML exports for search and rendering. Rebuilding CRDT state from JSON snapshots loses concurrent history and breaks offline merge.

3. **Design awareness alongside content.** Cursors, selections, presence, and comments ride on the same connection (Yjs awareness protocol) but are ephemeral — never persist them. Render remote cursors as a decoration layer (never DOM overlays that fight scroll), keyed by user id with stable colors.

4. **Decide server topology early.** A relay (websocket server forwarding encoded updates, e.g., y-websocket, Hocuspocus, Liveblocks) is the default; it needs no document parsing, only auth and persistence hooks. Read the websocket-realtime-ui-patterns article for the connection lifecycle, reconnect, and backoff concerns — the editor adds "flush queued local updates on reconnect" to that list.

## Persistence, Serialization, and Extensibility

1. **Version the document format.** Node schemas evolve (you will add node types and attributes); store a schema version with each document and write migrations. TipTap/ProseMirror JSON and Lexical JSON both tolerate additive change but break on renames/removals without migration code.

2. **Render read views without an editor.** Server-side and static rendering of documents should use the serializer path (model → HTML/React tree) with a sanitization pass, never an editor instance. This keeps read paths fast, safe (schema-constrained output), and usable for emails, search indexing, and OG previews.

3. **Sanitize at every boundary.** Paste ingestion, programmatic setContent, and server-side rendering each re-encode the model through the schema; still run an allowlist sanitizer on emitted HTML (the schema constrains structure, but attribute values — like hrefs — need explicit URL validation to block javascript: URIs).

4. **Test with the editor's real enemies.** IME input (Chinese/Japanese/Korean composition), undo/redo through every custom feature, paste from Word/Google Docs/Excel, selection across custom atomic nodes, rapid concurrent edits in two tabs, and caret position after AI-driven programmatic insertions. These six scenarios find more editor bugs than all happy-path tests combined.
