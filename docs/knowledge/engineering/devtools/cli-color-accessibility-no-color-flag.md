# Cli Color Accessibility No Color Flag

Terminal color is an accessibility surface, not decoration. Roughly one
in twelve men and one in two hundred women have some form of color
vision deficiency; many more run terminals where the palette is
unreadable (light themes receiving cyan, solarized schemes receiving
pure red), pipe output into logs, or use screen readers and braille
displays where escape sequences are spoken as garbage. The CLI Colors
standard makes this tractable with two contracts: every tool honors
`NO_COLOR` to disable color entirely, and color is only emitted when
the output is an interactive terminal. A tool that gets these two rules
right is usable everywhere; a tool that hardcodes `\\u001b[31m` into
its failure path is unreadable for a measurable fraction of its users
and corrupts every log file it touches.

## Scope

Designing color behavior in command-line tools: the `NO_COLOR`
convention, terminal detection, fallbacks for non-TTY output,
color-blind-safe palette selection, and alternative signaling that does
not depend on hue. Applies to tools written in any language. Not
covered: web UI contrast or full WCAG analysis.

## Workflow or implementation guidance

1. **Implement the `NO_COLOR` contract.** The convention is precise and
   short: when the environment variable `NO_COLOR` is set to any
   non-empty value, the tool emits no ANSI color escape sequences. No
   value parsing, no truthiness debates — presence of a non-empty value
   disables color. Pair it with explicit override flags so users and
   CI can force the other direction:

   ```text
   NO_COLOR=1 (any non-empty)  ->  color off
   --color=never               ->  color off, wins over env
   --color=always              ->  color on even when piped
   --color=auto (default)      ->  color on only if stdout is a TTY
   ```

2. **Detect the terminal, not the platform.** Color-on-by-default must
   be gated on the output stream being an interactive terminal
   (`isatty`-style check on stdout, or the standard-library equivalent),
   and on the `TERM` environment not being `dumb`. Checking platform or
   shell instead of the stream is the classic bug: `tool | grep` then
   embeds escape codes into a file.
3. **Never let decoration carry meaning alone.** Every status
   communicated with color needs a redundant channel: a prefix word
   (`error:`, `warn:`), an exit code, a symbol, or a structural column.
   The failing build line must read correctly through `NO_COLOR`, a
   monochrome printout, and a color-blind terminal:

   ```text
   error: typecheck failed  (src/worker.ts:41)   [x]
   ok:     812 tests passed                      [ ]
   ```

4. **Choose a color-blind-safe palette.** Prefer blue/orange or
   cyan/orange pairs over red/green for two-state signals; red/green is
   the single most common CLI accessibility failure because it encodes
   pass/fail on exactly the axis many users cannot separate. When red
   for errors and green for success must stay (they are strong
   conventions), combine them with the prefix words from the previous
   rule so hue is a bonus, not the payload.
5. **Respect intensity and themes.** Dim text for secondary
   information is a common footgun: on some terminals the dim escape
   renders nearly invisible against dark backgrounds. Test the palette
   on at least one light and one dark scheme; if dim text must exist,
   keep it to non-essential annotations.
6. **Handle combined-stream and redirected cases.** When stderr is
   colored but stdout is piped, gate each stream independently; a tool
   writing to stderr interactively while stdout feeds a log should keep
   stderr colored and stdout clean. Also strip color from any path that
   builds machine-readable output (JSON, CSV, TAP), which belongs to
   parsers, not eyes.
7. **Test the contract in CI.** Automated checks for this behavior are
   cheap: run the tool under `NO_COLOR=1` and assert the output
   contains no `ESC[` sequences; run it piped and assert the same; run
   it with `--color=always` piped and assert color is present. Three
   assertions, no flakiness, permanent protection.

## Controls

- **One color-decision point.** Centralize detection and emission in a
   single module or an established terminal-styling library rather than
   scattering escape sequences; the contract is only enforceable when
   one code path can be tested for it.
- **Env precedence documented.** Document in `--help` how `NO_COLOR`,
   `FORCE_COLOR`-style variables, `TERM=dumb`, and the `--color` flag
   interact, and keep the documented order stable across releases.
- **Palette review.** Include one screenshot or rendered sample of the
   tool's output in the repository docs so palette changes get seen by
   humans with different vision during review, not merged blind.
- **Log safety.** Anything the tool writes to files on the user's
   behalf (reports, caches) is always plain text regardless of flags.

## Validation evidence

1. `NO_COLOR=1 tool | cat -v` produces output with no `^[[` escape
   sequences visible — `cat -v` renders escapes visible, making their
   absence verifiable by eye and by `grep`.
2. `tool | cat -v` (piped, no env var) is likewise escape-free under
   `--color=auto` default behavior, proving TTY gating works.
3. `tool --color=always | cat -v` shows escape sequences, proving the
   override reaches the same single decision point.
4. `TERM=dumb tool` produces plain output even on an interactive
   terminal, proving the fallback for minimal terminals.
5. A grayscale print or a color-blindness simulation filter of the
   tool's failure output still distinguishes errors from successes via
   prefix and symbols alone.
6. In CI, the three assertions from the first three checks run as
   scripted tests on every pull request touching output code.

## Failure modes and correction

- **Escape codes in log files.** Somewhere bypassed the central
   decision point and wrote raw sequences. Grep the codebase for
   literal escape bytes and move the offending emission into the shared
   module.
- **`NO_COLOR` partially honored.** Color disappears from one subsystem
   but not another — two independent detection paths exist. Consolidate
   and re-test with the CI assertion.
- **Piped output still colored.** Detection checked stderr, or checked
   `isatty` before a pipe was established by the wrapper script; gate
   per-stream at write time.
- **Dark-theme users cannot see dim text.** Replace intensity
   differences with textual or structural differences; intensity can
   remain as enhancement only.
- **Windows legacy consoles garble output.** Older consoles without
   virtual-terminal processing need the escape sequences either enabled
   explicitly or the tool falls back to plain text; test on the oldest
   supported Windows terminal before shipping color there.

## Limitations

- `NO_COLOR` is a voluntary convention, not a standard enforced by any
  runtime; wrappers and dependencies that ignore it remain a problem,
  and piped output through such tools still carries escapes.
- Terminal rendering varies by emulator and theme; verification proves
  the contract (no escapes, redundant signaling), not visual quality on
  every terminal.
- User styling libraries change flag spellings and env-var behavior
  over time; re-verify the documented precedence after upgrades.

## Canonical sources

- NO_COLOR initiative, the no-color.org standard: https://no-color.org/
- CLICOLORS convention (terminal detection and FORCE_COLOR-style
  variables): https://bixense.com/clicolors/
- termenv, a library implementing terminal detection and color profile
  support: https://github.com/muesli/termenv
