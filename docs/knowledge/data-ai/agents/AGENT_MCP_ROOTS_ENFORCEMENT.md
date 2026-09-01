# Agent MCP Roots Capability Enforcement

MCP roots are filesystem locations a client declares to a server: "here is where my work lives." Servers may use roots to focus search and indexing, but the declaration is advisory from the server's perspective, which makes it tempting to treat as cosmetic. Enforced properly, roots are the opposite: a client-side scope contract that constrains which paths servers may be given, which path arguments hosts will forward, and how far a server's file access can legitimately reach. This article covers declaring roots, validating path arguments against them, and enforcing the boundary at the host rather than trusting server goodwill.

## Scope

Applies to MCP clients and hosts that declare the `roots` capability and exchange `roots/list` requests and `roots/list_changed` notifications with servers. Covers path-scope enforcement for filesystem-touching tools and resources. It does not cover server authorization (OAuth scopes), non-filesystem URI schemes except as they interact with root declarations, or sandboxing of the server process itself, which is a separate isolation layer that should exist independently of roots.

## Workflow or implementation guidance

1. Model roots as a grant, not a description. Each root entry carries a URI (file scheme), an optional name, and, in the host's internal model, the principal who granted it and the grant's expiry. Root sets are per server, not global: a code-analysis server and a notes server should not receive identical roots.
2. Declare the minimum. A root covering an entire home directory is almost always wrong; declare the project directory, the workspace subdirectory, or the specific data folder the server needs. Revoke by sending an updated list via `roots/list_changed` semantics when a task finishes.
3. Canonicalize before comparing. Expand symlinks and junction points, resolve `..` segments, normalize case where the filesystem is case-insensitive, and handle 8.3 short names on Windows, drive-letter aliases, and UNC versus mapped-drive forms. Enforcement that compares raw strings is bypassable by construction.
4. Check containment with prefix semantics on canonical paths: the candidate path must equal a root or fall under it as a directory component, not merely start with the root's characters (a sibling directory named `project-evil` next to a root directory named `project` is not inside it).
5. Gate every outgoing path argument. Before a `tools/call` leaves the host, extract every parameter the tool contract marks as a path or file URI, canonicalize it, and test containment against the roots granted to that server. Non-contained arguments fail closed with a specific error naming the allowed roots.
6. Treat returned paths with suspicion too. Results containing file URIs or paths that point outside the granted roots are flagged, not dereferenced by the host on the server's behalf in follow-up calls.
7. Handle root changes atomically. When roots shrink, in-flight requests referencing now-out-of-scope paths are rejected on their next turn; caches or indexes a server built from the old roots are the server's problem, but the host must not keep supplying fresh out-of-scope data.
8. Audit the boundary: every containment check logs the requesting server, the tool, the raw argument, the canonicalized path, the matched root, and the verdict. Rejections are first-class signals for detection, not noise to suppress.

## Controls

- Root grants flow through the same review as tool permissions: a user or admin approves the root set when adding a server, and changes require re-approval.
- Canonicalization is centralized in one vetted path library per platform; ad hoc string normalization inside tool adapters is prohibited.
- Per-server root count and depth ceilings limit blast radius and keep `roots/list` responses bounded.
- A denylist overlay handles escape hatches the canonicalizer cannot close, such as filesystems reachable through device paths or network reparse points on Windows.
- Detection rules alert on repeated containment rejections from one server, which is the signature of probing behavior.

## Validation evidence

- Path-escape fixture suite: `../` chains, absolute paths outside roots, symlinked directories pointing outside, junction and subst aliases on Windows, case-variant paths, trailing-dot and trailing-space variants, UNC forms, and paths that merely share a prefix with a root. Every fixture must be rejected with the canonicalization reason recorded.
- Positive fixtures: files directly in a root, nested subdirectories, and paths reaching a root through an in-scope symlink must pass.
- Round-trip tests for root changes: shrinking a root mid-session and verifying the next out-of-scope call fails while in-scope calls continue.
- Evidence for auditors: sample audit records showing raw-versus-canonical divergence, plus a mapping from each connected server to its current root set and approver.

## Failure modes and correction

- A tool contract marks a parameter as generic string when it is actually a path, bypassing the gate. Correction: contract review requires path-typed parameters to be declared, and heuristic post-hoc scanning flags path-shaped strings passed to known file tools.
- The canonicalizer resolves through a symlink the attacker can create after the check (time-of-check to time-of-use). Correction: open files with no-symlink-follow semantics where the platform offers it, or re-verify after open.
- Users grant `/` or a home directory to make an error go away. Correction: the approval UI shows what files become reachable and requires an explicit justification for over-broad roots.
- Root revocation never propagates because `roots/list_changed` notifications are dropped. Correction: servers must re-list roots before out-of-scope operations succeed, and the host re-serves the current list on reconnect.

## Limitations

Roots constrain path arguments the host can see; a server with arbitrary network access can read files other ways, so roots are a scope contract, not a sandbox. TOCTOU races cannot be fully closed at the argument layer. Cross-platform path semantics (Windows device namespaces, case folding) make canonicalization a maintenance burden with real bug surface. And because roots are advisory for servers, a non-cooperating server simply ignores the hint, which is fine as long as the host enforces containment on everything it forwards.

## Canonical sources

- Model Context Protocol specification, Client Roots: https://spec.modelcontextprotocol.io/specification/2025-11-25/client/roots
- OWASP, Path Traversal: https://owasp.org/www-community/attacks/Path_Traversal
- OWASP Cheat Sheet Series: https://cheatsheetseries.owasp.org/
