# os-command-injection-prevention

**Issue:** OS command injection (CWE-78) occurs when an application passes attacker-controlled data into a command that is executed through an operating system shell. Because shells interpret metacharacters such as semicolons, backticks, pipes, and substitution expressions, a parameter like a filename, hostname, or user-supplied string can escape its intended argument position and execute arbitrary commands with the privileges of the application process. Despite being one of the oldest vulnerability classes, it remains a frequent cause of critical findings in image and document processing pipelines, DevOps tooling, and AI agent runbooks, and it consistently ranks in OWASP Top 10 injection categories. Prevention is architectural first and validation second: the safest design avoids spawning a shell at all.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Root causes

1. **Shell string interpolation.** Building a command as a single string that mixes fixed text with user input, then executing it via sh -c, exec, os.system, backticks, or shell=True variants, lets every shell metacharacter in the input change the command's meaning.
2. **Argument injection on safe commands.** Even when the command name is fixed, user input placed among arguments can inject flags such as --config, -o, or an @file reference that turns a benign tool into one that reads or writes arbitrary files, so argument-level validation is still required.
3. **Confusing encoding with safety.** Escaping quotes or stripping a blocklist of metacharacters is fragile across shells and encodings: newlines, unicode look-alikes, environment variable expansions, and shell-specific syntax defeat naive filters, and blocklists drift behind shell features.
4. **Shellout by habit.** Reaching for curl, tar, ffmpeg, or git via subprocess instead of using the language's native library equivalent imports the entire shell grammar and the tool's own scripting features into the trust boundary.

## Primary defenses

1. **Prefer native library APIs.** Replace subprocess calls with in-process equivalents: language HTTP clients instead of curl, archive libraries instead of tar, SDK clients instead of cloud CLIs. This removes both the shell and the external tool from the attack surface.
2. **Spawn without a shell and pass an argument array.** When a real binary is required, use execve-style APIs that take argv arrays (spawn with shell disabled, execFile, subprocess.run with shell=False) so each value is delivered to the target program as data, never interpreted by a shell.
3. **Keep the command path out of user hands.** Select the executable from a hardcoded constant or a server-side allowlist keyed by an opaque identifier the client sends; never let input choose the program name or its path.
4. **Validate every argument against a strict safelist.** Accept only values matching a tight pattern for the specific slot, such as ^[a-zA-Z0-9._-]{1,64}$ for filenames or a parsed and re-serialized URL for fetch targets, and reject anything else before the process is created.
5. **Send data via stdin, not argv.** For tools that accept content on standard input, pipe the payload instead of placing it on the command line; this keeps it out of argument injection range and out of process listings.

## Hardening and containment

1. **Least-privilege execution.** Run command-spawning workers as a dedicated low-privilege service account with no shell for interactive login, minimal filesystem scope, and no ambient credentials, so a successful injection has little to steal and little to reach.
2. **Sandbox the execution environment.** Container or sandbox isolation with read-only filesystems, dropped capabilities, seccomp or platform equivalents, and egress deny-by-default networks converts an injection from full compromise into a contained event.
3. **Pin tool versions and audit argument surface.** Document which external binaries are allowed, pin their versions, and review their argument grammar during upgrades, because new flags can reopen argument injection paths in previously reviewed code.
4. **Enforce resource limits.** CPU, memory, wall-clock, and output-size limits on spawned processes prevent an injected command from becoming a resource-exhaustion vector against the host.

## Detection and testing

1. **Static analysis gates.** Flag shell=True, os.system, Runtime.exec with concatenated strings, and backtick usage in CI, requiring an explicit allowlist annotation to merge code that spawns processes.
2. **Metacharacter and flag fuzzing in tests.** Unit and integration tests should feed separators, quotes, newlines, doubled dashes, and leading dashes into every argument position and assert the child process received them verbatim as data, not as syntax.
3. **Command audit logging.** Log the exact argv array, triggering request ID, and identity for every spawned process so incident response can reconstruct what ran without needing shell-level logging on hosts.
4. **Runtime egress and execution monitoring.** Alert on spawned processes whose binary, parent, or network destination deviates from the allowlist; unexpected curl, nc, or interpreter spawns from a web worker are a strong injection signal.

## References informing this article

1. **OWASP OS Command Injection Defense Cheat Sheet.** Core guidance on avoiding shell invocation, argument arrays, safelists, and the argument injection variant.
2. **matklad, "echo Shell Injection".** Technical explanation of why argv-array execution prevents metacharacter interpretation.
3. **StackHawk 2025 command injection guide.** Current attack mechanics and prevention patterns for modern stacks.
4. **Fastly, "Back to Basics: OS Command Injection".** Defense-in-depth framing for input validation and least privilege.
