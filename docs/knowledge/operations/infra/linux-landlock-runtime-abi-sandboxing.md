# Linux Landlock runtime ABI sandboxing

**Issue:** An application may retain ambient filesystem or network access beyond its intended behavior even without elevated privileges.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

Use Landlock as an additional stackable restriction layer for processes that can self-sandbox. Detect the supported ABI and errata at runtime, request only access rights known to that ABI, and allowlist only required paths and TCP operations. Verify the kernel build and boot configuration enable Landlock. Define a deliberate fallback: sensitive execution fails closed when its required sandbox is unavailable; any compatibility mode emits an unmistakable signal and requires approval.

Apply the ruleset before attacker-controlled input and ensure child processes inherit the restricted domain. Keep system-wide MAC, namespaces, seccomp, capabilities, and ordinary permissions because Landlock complements rather than replaces them.

## Verification

Test the oldest and newest supported ABIs. Confirm allowed operations succeed and denied operations fail. Cover rename and cross-directory cases, child inheritance, unavailable-Landlock behavior, and startup reporting without sensitive paths.

## Gotchas

- Access bits not declared as handled are not denied.
- Do not assume newer ABI features on older kernels.
- Handles opened before sandbox enforcement remain usable.

## Official source

- [Linux kernel Landlock documentation](https://docs.kernel.org/userspace-api/landlock.html)
