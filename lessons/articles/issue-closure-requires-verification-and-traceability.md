# Issue closure requires verification and traceability

**Category:** Lessons
**Author:** ORCHORDS
**Source:** [example project issue tracking workflow](https://github.com/example-org/example-repo)

## Lesson

An issue is not complete merely because code was changed. Closing it should leave enough evidence to understand what was fixed, how it was checked, and where the implementation lives.

## Practice

- Search both open and closed work before filing a new issue; reopen a regression instead of duplicating it.
- Record location, reproducible problem, root cause, and a scoped fix.
- Assign ownership and exactly one planning bucket so status reporting is based on the issue system, not memory.
- Before closure, add the verification performed and the commit identifier containing the fix.
- Keep partially addressed work open with a progress update rather than closing it as complete.

## Verification

Audit a completed issue and confirm that an independent reviewer can locate the change and repeat the stated verification without relying on private chat context.

## Failure modes

- Duplicate tickets divide history and make regressions hard to spot.
- Fixed issues lack evidence and cannot be audited.
- Dashboard metrics undercount work because planning metadata is optional.
