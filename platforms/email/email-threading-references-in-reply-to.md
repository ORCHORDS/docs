# email-threading-references-in-reply-to

**Issue:** Grouping inbound messages into conversations — for a support ticket system, a shared inbox, or a mail client — requires reconstructing the reply tree from RFC 5322 headers. The `In-Reply-To` and `References` headers are the canonical mechanism, but they are optional, frequently malformed, silently dropped by some clients and webmailers, and must be *written* correctly by your own system when it sends replies or automated responses. Systems that thread naively (by subject line) mis-group, split threads, or loop messages; systems that thread correctly handle broken input and still converge on the right conversation. This is the JWZ threading problem, and it recurs in every product that touches conversations over email.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The headers and their semantics

1. **Message-ID is the anchor.** Every message you send must carry a globally unique `Message-ID` of the form `<random@yourdomain.com>`. Threading is impossible for messages without one; generate IDs yourself, never trust that upstream MUAs added them.
2. **In-Reply-To names the direct parent.** Per RFC 5322 section 3.6.4 it holds the Message-ID(s) of the message(s) being replied to (historically it could hold more than one, so parse it as a list, not a scalar).
3. **References is the full ancestor chain.** A colon-free sequence of parent Message-IDs, oldest first, ending with the direct parent. When replying, the correct behavior is: copy the parent's entire `References`, append the parent's own `Message-ID`, and set the result as your `References` header. Keep only the last entry in `In-Reply-To`.
4. **Nothing is guaranteed.** Clients delete headers, mailing lists mangle them, users reply from different accounts, and some webmail systems omit `References` entirely. Your threading must treat all headers as hints to be reconciled, not a trustworthy tree.

## Building threads (JWZ algorithm)

1. **Pass 1: link by References.** For each message, walk its `References` list and link consecutive IDs as parent/child in a container table (containers exist even for IDs you have not seen, representing missing messages). `References` is authoritative about ordering where present.
2. **Pass 2: fill gaps with In-Reply-To.** If a message has no `References`, use `In-Reply-To`'s last valid Message-ID as its parent. Thunderbird-class clients build the tree from References first and fall back to In-Reply-To, which is the behavior users expect.
3. **Pass 3: resolve duplicates and loops.** If a message already has a parent from a different path, prefer the References-derived link and demote the other to a secondary child; break any cycles (A referencing B referencing A) by treating the later message as a root of a new branch rather than crashing or dropping it.
4. **Pass 4: prune empty containers.** Containers with no message and only one child are spliced out (the child is promoted). Containers with no message and multiple children are retained as "dummy" group nodes only if that keeps siblings together.
5. **Pass 5: group roots into conversations.** Sort roots by date; a thread is the connected component. For UI purposes, define conversation identity by root Message-ID, and store a stable `thread_id` so late-arriving messages with only partial hints can still join via any known ancestor ID in the container table.

## Writing correct headers when you send

1. **Reply with the full chain.** Outbound replies from your system must set `In-Reply-To` to the parent's Message-ID and `References` to the parent's References plus the parent's Message-ID — truncated or missing References breaks threading for everyone downstream.
2. **Never reuse Message-IDs.** Each outbound message (including each automated notification in a sequence) gets a fresh ID; reusing an ID across template renders makes clients collapse distinct messages into one thread entry.
3. **Decide intentionally for new conversations.** A fresh campaign or notification that should *not* join an existing thread must omit both headers — but a "reply" to a user's inbound email (ticket update, NDR-style follow-up) should thread under it, keeping the conversation together in the user's client.
4. **Preserve inbound Message-IDs in storage.** Keep the raw Message-ID text (including angle brackets and any malformed whitespace) as the join key; normalizing inconsistently is a classic way to split a thread in half.
5. **Do not thread by subject.** Subject lines mutate ("Re:", localization, trimming) and unrelated messages share subjects. Subject grouping is only a last-ditch fallback for messages with no headers at all, and should be gated by participants overlap.

## Handling broken and hostile input

1. **Validate Message-ID shape before trusting it.** Accept `<local@domain>` tokens; discard anything without an `@`, over-long, or containing control characters/newlines (a header-injection vector if you ever re-emit it). Limit `References` to a sane length (some clients let it grow unboundedly; RFC guidance says to prune from the front, keeping the newest entries).
2. **Deduplicate arrival paths.** The same Message-ID can reach you twice (multiple recipients, CC to an alias, IMAP re-fetch). Idempotent ingestion keyed on Message-ID + folder prevents ghost duplicates in the tree.
3. **Bound thread size and depth.** Deep or wide threads (thousands of messages) make naive recursive algorithms blow stacks; iterate and cap rendering depth, and consider "collapse old branches" UX for conversations that outgrow usefulness.
4. **Reconcile late arrivals lazily.** Messages arriving out of order must be able to attach under a container that already exists — this falls out of the container-table design, but persistence layers that snapshot the tree eagerly need explicit re-computation triggers.
5. **Test against real-world corpora.** Unit tests with pristine headers pass while production breaks: build a fixture corpus from real tickets including Outlook-exchange threads, Apple Mail, Gmail, and mailing-list mangles (list software rewrites Subjects and sometimes drops References). Ready-made implementations (Python `JWZThreading`/`threadweave`, Rust `mail-threading`) encode these lessons already — prefer porting their test cases over inventing your own from scratch.

## Storage and product integration

1. **Materialize the thread identity.** Store `thread_id`, `parent_id`, and depth as columns updated on ingestion, so conversation views are a single indexed query rather than runtime graph assembly.
2. **Handle merges and splits.** When new evidence arrives (a message arrives whose References reveal two tickets are one conversation), support merging `thread_id`s as an explicit, logged operation — auto-merging support tickets can fuse two customers' conversations, a privacy incident.
3. **Respect threading for automation decisions.** "First reply in a new thread" vs "reply inside existing thread" changes open rates and support workflows; make threading headers a first-class part of notification template design, not an accident of whichever mail library default you inherited.
4. **Cross-reference with IMAP THREAD when available.** If you ingest from IMAP, servers exposing `THREAD=REFERENCES` (RFC 5256) can do server-side threading to cross-check yours — useful as a conformance oracle, not as the only mechanism (server support is uneven).
