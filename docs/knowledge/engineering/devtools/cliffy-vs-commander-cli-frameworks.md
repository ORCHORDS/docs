# Cliffy Vs Commander Cli Frameworks

Commander is the incumbent Node.js CLI framework: a mature, minimal
library behind tools like the Vue CLI and countless internal scripts.
Cliffy is the Deno-native upstart that grew into a full-featured
framework for both Deno and Node: subcommands, type-safe options via
TypeScript generics, interactive prompts, completion generation, and a
composable command-module model. Choosing between them is a decision
about runtime commitment, type-safety appetite, and how much of the CLI
surface area (help, prompts, shell completion) you want the framework
to own versus assemble from small libraries.

## Scope

Comparing Commander and Cliffy for building command-line tools in
TypeScript/JavaScript: installation and runtime model, command and
option definition, type inference, interactive features, completions,
testing, and maintenance posture. Applies to new tool decisions and to
migrations. Not covered: argument parsing micro-libraries (yargs,
cac) or non-JS ecosystems.

## Workflow or implementation guidance

1. **Start from the runtime commitment.** Commander is an npm package
   with zero runtime assumptions and runs wherever Node runs, including
   bundlers, single-executable Node apps, and CI. Cliffy originated in
   the Deno ecosystem and is also consumable from Node via npm-style
   imports; if your organization standardizes on Deno or wants one CLI
   codebase for both runtimes, Cliffy's design fits natively, while
   Commander remains the safest bet for Node-only or bundler-embedded
   CLIs.
2. **Define commands the framework's way.** Commander chains action
   handlers onto declaratively parsed options:

   ```js
   const program = require('commander');
   program
     .name('deploy')
     .command('worker')
     .requiredOption('-e, --env <env>', 'target environment')
     .option('--dry-run', 'validate only', false)
     .action(async (opts) => { await deployWorker(opts); });
   ```

   Cliffy models each command as a class with typed fields, where
   option types are declared through generic parameters and consumed as
   strongly typed properties. The practical difference: Commander's
   options arrive as an untyped-to-loosely-typed object you validate
   yourself; Cliffy's arrive pre-typed from the declaration, so
   `opts.env` is a string and `opts.dryRun` is a boolean because the
   framework inferred it.
3. **Assess type safety honestly.** Commander accepts TypeScript and
   can be typed through interfaces and option-parsing helpers, but the
   guarantees are conventions you maintain. Cliffy's value proposition
   is that the option definition is the type: numbers parse to numbers,
   enums restrict choices, and the handler receives types derived from
   the declaration. For CLIs where misparsed flags cause damage
   (deploy tools, destructive migrations), that inference removes a
   class of runtime surprises.
4. **Evaluate interactive surface.** Cliffy ships prompts, select and
   checkbox lists, secret input, and confirm flows as first-class
   framework parts, which suits developer-facing tools that ask
   questions. Commander is deliberately unopinionated: you pair it with
   whatever prompt library you like (or none, because the tool is
   script-first). Prefer script-first with Commander when automation is
   the primary consumer; prefer built-in prompts with Cliffy when
   humans drive the tool interactively.
5. **Handle help, completion, and errors as framework features.** Both
   generate help from definitions; Commander's help is customizable
   through event hooks and formatting functions, while Cliffy generates
   help, shell completion scripts, and clickable-styled output from the
   command tree. If your tool's users expect tab completion out of the
   box, Cliffy provides it without an extra dependency; with Commander
   you add a completion library and wire it yourself.
6. **Structure large CLIs for growth.** Commander scales through
   standalone program instances per subcommand file, composed at
   startup. Cliffy scales through a command registry where each
   subcommand is a module registered by path, which maps naturally to
   lazy loading. For a monorepo CLI with dozens of subcommands, the
   Cliffy registry avoids importing every command for every invocation;
   with Commander, do the equivalent by importing subcommand modules
   lazily inside their parent command's action.
7. **Test both the same way.** The portable pattern is to invoke the
   program against argv and captured stdout/stderr in-process, asserting
   exit codes and output. Commander's program object makes this
   straightforward; Cliffy supports instantiation with injected
   arguments for test runs. Avoid spawning real processes per test
   where possible — startup dominates runtime on Windows.

## Controls

- **One framework per repository.** Mixed CLI frameworks in one
  monorepo double the upgrade and security-review surface; pick one and
  codify it in the template that scaffolds new tools.
- **Pin and audit.** Both are dependencies of developer tooling with
  broad transitive reach; pin exact versions in the lockfile and treat
  CLI dependency bumps as reviewed changes, not automated ones.
- **Exit code contract.** Whichever framework is chosen, define the
  exit-code policy (zero success, non-zero categories) in one module
  both frameworks' handlers call, so scripts and CI can rely on it.
- **Help-text review.** Help is the tool's interface; include generated
  help output in pull requests that add options so reviewers see what
  users will see.

## Validation evidence

1. A scaffolded command in each framework produces working `--help`,
   parses a typed option, and rejects an unknown flag with non-zero
   exit — the ten-minute smoke test that tells you the DX claims hold
   in your environment.
2. For Cliffy, compile the project with strict TypeScript and confirm
   the handler's options object carries the declared types; assign a
   wrong type in a test file and confirm the compiler rejects it.
3. For Commander, add an integration test that runs the command with a
   missing required option and asserts both the non-zero exit code and
   the human-readable error on stderr.
4. Interactive flows: run the prompt path with piped stdin and confirm
   the tool either reads answers from stdin or degrades to flags —
   CLIs that hang waiting for a TTY in CI are the standard failure.
5. Completion (Cliffy): generate the completion script, source it in a
   scratch shell, and confirm the tool's subcommands complete.

## Failure modes and correction

- **Commander options are `undefined` in handlers.** The action
   signature shifted across major versions (variadic args position);
   pin the major and read the handler signature for that version
   rather than copying snippets from other projects.
- **Cliffy type inference degrades to loose types.** Usually an option
   declared without a generic or with a union the framework cannot
   narrow; restate the option type explicitly rather than casting at
   the call site.
- **Prompts block CI.** Interactive paths must be optional: always
   provide flag equivalents, and detect non-TTY stdin to fail fast
   with a message naming the flags.
- **Bundle size explodes when embedding.** Commander is small and
   bundles cleanly; Cliffy's larger feature set pulls in more modules —
   import per-command modules rather than the framework root when
   bundling to a single binary.
- **Deno-to-Node drift.** Code written against Deno-style imports needs
  the npm-compat path to run under Node; keep one import convention per
  project and test both runtimes in CI if both are supported.

## Limitations

- This is not a performance decision: both parse argv in milliseconds;
   choose on API ergonomics, runtime fit, and feature scope.
- Cliffy's richest type-safety and completion features assume
  TypeScript; in plain JavaScript the gap with Commander narrows to
  feature set and style preference.
- Commander's enormous install base means more Stack Overflow answers
  but also more version-mismatched advice; either way, verify against
  the pinned version's documentation.

## Canonical sources

- Commander.js GitHub repository (tj/commander.js): https://github.com/tj/commander.js
- Cliffy documentation site: https://cliffy.io/
- Cliffy GitHub repository (c4spar/cliffy): https://github.com/c4spar/cliffy
- Deno Manual (Cliffy's home runtime ecosystem): https://deno.com/manual
