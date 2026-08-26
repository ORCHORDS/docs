# audio-transcription-whisper

**Issue:** Whisper transcription accuracy drops for accented speech, technical jargon, and noisy environments
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A meeting transcription service using Whisper produces transcripts with domain-specific term errors (product names, medical terminology) and poor speaker diarization for overlapping speech.

## Pattern / Solution
Use Whisper with `initial_prompt` containing domain vocabulary to bias decoding toward known terms. Pre-process audio: normalize volume, apply noise reduction (noisereduce library), split on silence for chunking. For diarization, combine Whisper with pyannote.audio. Use `word_timestamps=True` for alignment.

For production deployments, use `faster-whisper` (CTranslate2 backend) for 4x speedup with the same accuracy, or WhisperX for batching support.

## Gotchas
- Whisper hallucinates text on silent audio segments — detect silence and skip those chunks before transcription
- The `initial_prompt` token budget is limited (~224 tokens) — prioritize the most critical vocabulary terms
- Transcription accuracy varies significantly by language; some languages require the large-v3 model

## Related
- text-to-speech-patterns
- multimodal-vision-patterns
- llm-for-extraction
