# Tool Error Boundaries

Keep tool failures from silently contaminating the rest of an agent run.

## Checklist
- Classify retryable vs terminal failures.
- Preserve enough error context for recovery without leaking secrets.
- Bound retry counts and backoff.
- Escalate side-effect uncertainty instead of guessing success.

## Primary sources
- OpenAI `openai/openai-agents-python`.
- Cloudflare `cloudflare/agents`.
