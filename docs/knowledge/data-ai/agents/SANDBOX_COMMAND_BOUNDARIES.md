# Sandbox Command Boundaries

Define how command execution is constrained inside agent sandboxes.

## Checklist
- Separate inspection from modification commands.
- Keep working-directory assumptions explicit.
- Capture command exit status and relevant output.
- Stop on unexpected environment changes.

## Primary source
- OpenAI `openai/openai-agents-python` sandbox concepts.
