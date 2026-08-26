# text-to-speech-patterns

**Issue:** TTS integration introduces latency, voice inconsistency, and normalization complexity in production systems
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A voice assistant pipeline converts LLM text output to speech. The first word is cut off, pauses are wrong, and the voice sounds robotic on technical content. Latency from text to audible output exceeds 3 seconds.

## Pattern / Solution
Stream TTS: start audio playback as soon as the first chunk is received — do not wait for full synthesis. Pre-generate common phrases (greetings, confirmations) and cache them. Use sentence-boundary chunking to align TTS boundaries with natural speech. For long-form content, use SSML to control pacing and emphasis.

Choose provider based on use case: ElevenLabs for naturalness, Google TTS for latency, Coqui TTS for on-premise deployments.

## Gotchas
- Numbers, abbreviations, and URLs need normalization before TTS — "API" should read as "A P I", "$5.00" as "five dollars"
- Streaming TTS requires WebSocket or chunked HTTP — not all clients support it
- Voice cloning without explicit consent carries legal risk in many jurisdictions; verify before building features around it

## Related
- audio-transcription-whisper
- llm-streaming-responses
- llm-async-patterns
