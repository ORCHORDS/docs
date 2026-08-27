# Sandbox Workspace Manifest

Describe sandbox inputs and mounted resources explicitly before a long-running agent task starts.

## Checklist
- List repositories, files, and generated workspace entries.
- Keep workspace state reproducible.
- Avoid silently depending on host-local files.
- Review manifest changes with the task evidence.

## Primary source
- OpenAI `openai/openai-agents-python` sandbox-agent concepts.
