> Auto-generated from `Transcriber Pipeline.md` in the docs repo.

> Auto-generated from `Transcriber Pipeline.md` in the docs repo.

> Auto-generated from `Transcriber Pipeline.md` in the docs repo.

> Auto-generated from `Transcriber Pipeline.md` in the docs repo.

> Auto-generated from `docs/audio/TRANSCRIBER_PIPELINE.md` in the docs repo.

---
title: "Transcriber Pipeline"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# Transcriber Pipeline

**Project:** Beetle Studio  
**Owner:** Ryan Foster (Audio Systems Engineer)  
**Reviewers:** Kirk Beka (CTO), Daniel Kim (Effects), Maya Rodriguez (Backend)  
**ISO Standards:** ISO/IEC 12207:2017 (development), ISO/IEC 25010:2023 (functional suitability, performance efficiency), ISO/IEC 25023:2023 (measurement)  
**Version:** 1.3.0  
**Last Updated:** June 2026  

---

## Overview

The Transcriber Pipeline converts audio and video files into time-aligned text transcripts and subtitle files (SRT, WebVTT, ASS) suitable for import into Beetle Studio's timeline. Per **ISO/IEC 12207:2017 §6.1**, interface specifications must be documented. This document describes the pipeline's architecture, operational requirements, accuracy characteristics, and integration points.

The pipeline is implemented in `transcriber.py` and runs as a standalone command-line tool. It is not currently embedded inside the C++/Qt6 desktop application; integration into the main editor is planned for v3.5.0.

## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | Audio/video transcription subsystem: vocal separation, automatic speech recognition (ASR), voice activity detection (VAD), speaker diarization, subtitle export |
| **Diátaxis form** | Reference |
| **Primary audience** | Ryan Foster, Kirk Beka, Daniel Kim, Mooned Dev |
| **Secondary audience** | Future maintainers and reviewers of this document |

## Contents

- [Pipeline Stages](#pipeline-stages)
  - [Stage 1 — Audio Extraction](#stage-1--audio-extraction)
  - [Stage 2 — Vocal Separation (Demucs)](#stage-2--vocal-separation-demucs)
  - [Stage 3 — Voice Activity Detection](#stage-3--voice-activity-detection)
  - [Stage 4 — Speaker Diarization](#stage-4--speaker-diarization)
  - [Stage 5 — Speech Recognition (Whisper)](#stage-5--speech-recognition-whisper)
  - [Stage 6 — Hallucination Filtering and Cleanup](#stage-6--hallucination-filtering-and-cleanup)
  - [Stage 7 — Subtitle Export](#stage-7--subtitle-export)
- [Operational Requirements](#operational-requirements)
  - [Hardware Requirements](#hardware-requirements)
  - [Software Requirements](#software-requirements)
  - [Model Storage](#model-storage)
- [Performance Characteristics](#performance-characteristics)
- [Accuracy Characteristics](#accuracy-characteristics)
- [Command-Line Interface](#command-line-interface)
- [Output Files](#output-files)
- [Caching Behavior](#caching-behavior)
- [Integration Roadmap](#integration-roadmap)
- [Version History](#version-history)
  - [Change Log](#change-log)
  - [Review Cadence](#review-cadence)

---

## Pipeline Stages

The pipeline executes the following stages in order. Stages marked _optional_ are skipped unless the corresponding CLI flag is set.

### Stage 1 — Audio Extraction

- **Input:** any media file supported by FFmpeg (MP4, MKV, MOV, MP3, WAV, FLAC)
- **Output:** two WAV files
  - `input_44k.wav` — 44.1 kHz stereo, passed to Demucs
  - `input_16k.wav` — 16 kHz mono, passed to Whisper
- **Optional normalization:** EBU R128 loudness normalization (`--normalize`) to `-23 LUFS`
- **Failure mode:** returns non-zero exit code if FFmpeg is missing or input is unreadable

### Stage 2 — Vocal Separation (Demucs)

- **Tool:** Facebook Demucs v4 with selectable model variant
- **Default model:** `htdemucs` (4-stem: vocals, drums, bass, other)
- **Alternative models:**
  - `htdemucs_ft` — fine-tuned, better for rap/music-heavy content
  - `htdemucs_6s` — 6-stem variant (adds piano, guitar)
  - `hdemucs_mmi` — hybrid model
- **Skip flag:** `--no-sep` skips Demucs entirely; Whisper runs on the raw mix
- **Output:** `demucs/vocals.wav` and three other stems
- **Typical runtime:** 30–60 s per minute of input on RTX 3060

### Stage 3 — Voice Activity Detection

- **Tool:** Silero VAD (built into Demucs distribution)
- **Flag:** `--vad`
- **Output:** list of speech segments `{start_s, end_s, duration_s}`
- **Effect:** when enabled, downstream Whisper transcription runs on each detected segment independently rather than on the full audio. This dramatically reduces hallucination on music-only and silent sections.

### Stage 4 — Speaker Diarization

- **Tools:** Resemblyzer (speaker embeddings) + SpectralCluster (clustering)
- **Flag:** `--diarize`
- **Optional:** `--num-speakers N` to constrain the cluster count; if omitted, the clusterer estimates automatically
- **Output:** `speaker_segments` list in `transcript.json`
- **Effect:** assigns speaker labels (`SPEAKER_00`, `SPEAKER_01`, …) to each ASR chunk

### Stage 5 — Speech Recognition (Whisper)

- **Tool:** OpenAI Whisper via HuggingFace Transformers
- **Default model:** `openai/whisper-medium.en` (English, 769 M parameters)
- **Multilingual:** `openai/whisper-medium` for non-English content
- **Large-v3 (highest quality):** `openai/whisper-large-v3` (1.55 B parameters, English) or `openai/whisper-large-v3` (multilingual). ~10 GB VRAM. Highest available accuracy; significantly better on Chinese/Japanese/Korean.
- **Fast model option:** `distil-whisper/distil-large-v3` (6× faster than large-v3 with similar quality, available via `--fast` flag)
- **Optional:** `openai/whisper-small` plus the FLEURS-fine-tuned LoRA adapter at `C:\SenseVoiceModels\whisper_ft_en_ru`
- **Decoding strategy:** temperature fallback chain `[0.0, 0.2, 0.4, 0.6, 0.8, 1.0]` to escape greedy-decoding failures on music and accented speech. Disable with `--no-temperature`.
- **Multi-pass decoding:** `--multi-pass` runs 3 decoding passes with temperatures `[0.0, 0.2, 0.4]` and votes on the result with the highest unique-word ratio. Improves finance/numbers-heavy content by ~5% WER. Slower by ~20%.
- **Chunking:** `chunk_length_s=30` with `stride_length_s=(6, 0)` for long-form transcription
- **Optional word-level timestamps:** `--word-level` switches return mode to `"word"` (emits `subtitles_word.srt`)

### Stage 6 — Hallucination Filtering and Cleanup

The pipeline applies a multi-signal hallucination detector that returns a confidence score (0.0–1.0). A chunk is rejected if any of these signals exceed its threshold:

| Signal | Threshold | Catches |
|---|---|---|
| Phrase match | 0.85+ | Common Whisper loops: `thank you for watching`, `subscribe to my channel`, `bye bye` |
| Consecutive repeats | 0.9 | `foreign foreign foreign`, `form form form` |
| Repetition ratio | 0.85 | One word dominating the chunk (`the the the the...`) |
| Repeated pairs | 0.8 | `X X X` patterns |
| Unique-word ratio | 0.85 | Low information content |
| Special char density | 0.7 | `((()))` etc. |
| Audio RMS + text length | 0.85 | Silent audio producing verbose text (Whisper fills silence) |
| Words-per-second | 0.7 | Unrealistic speech rate (>5 wps) |
| Avg logprob (from Whisper) | 0.75 | Low-confidence transcriptions |
| Compression ratio | 0.8 | High-repetition decode outputs |

The detector returns `(is_hallucination, reason, confidence)` for logging and audit purposes.

- **Deduplication:** Jaccard similarity ≥ 0.6 between adjacent chunks triggers removal of the duplicate
- **Text cleanup:** sentence capitalization, contraction normalization, repeated-word collapse, number/currency formatting (`2.3 %` → `2.3%`, `$ 100` → `$100`)
- **Optional LLM post-correction:** `--llm-correct` passes the final transcript through GPT-4o-mini for context-aware cleanup. Requires `OPENAI_API_KEY` environment variable.

### Stage 7 — Subtitle Export

- **SRT:** sentence-aware grouping with two constraints:
  - max 84 characters or 6 seconds per block
  - max 21 characters per second reading speed (BBC accessibility standard) — extends block duration automatically when text is dense
- **WebVTT:** identical timing to SRT with comma-to-dot timestamp conversion
- **ASS:** Advanced SubStation Alpha format, video-editor compatible
- **Optional word-level SRT:** 8-word blocks with `min_duration_s=1.5`
- **SFX tags:** the exporter detects and surfaces 50+ Whisper sound-effect tags (`[music]`, `[laughter]`, `[applause]`, `[door slam]`, `[phone ringing]`, `[breathing]`, etc.) as inline labels in the SRT block.

---

## Operational Requirements

### Hardware Requirements

| Component | Minimum | Recommended |
|---|---|---|
| GPU | NVIDIA with 6 GB VRAM, CUDA 11.8+ | NVIDIA RTX 3060 12 GB or better |
| VRAM by model | small: 2 GB; medium.en: 5 GB; large-v3: 10 GB | medium.en on RTX 3060 leaves 7 GB headroom |
| System RAM | 8 GB | 16 GB |
| Disk | 8 GB free | 15 GB free (for model cache) |

CPU-only mode is supported but is 5–10× slower than GPU mode and is not recommended for production use.

### Software Requirements

| Software | Version | Notes |
|---|---|---|
| Python | 3.10+ | 3.11 recommended |
| PyTorch | 2.5+ with CUDA 12.1 | Matches `torch 2.5.1+cu121` build used in development |
| Transformers | 4.45+ | HuggingFace |
| Demucs | latest | `pip install demucs` |
| FFmpeg | any recent | Binary at `C:\Tools\ffmpeg\ffmpeg-master-latest-win64-gpl\bin\ffmpeg.exe` |
| Silero VAD | bundled with Demucs | no separate install |
| Resemblyzer | latest | `pip install resemblyzer` |
| SpectralCluster | latest | `pip install spectralcluster` |
| jiwer | latest | optional, for WER measurement |
| edge-tts | latest | optional, for regenerating test scenarios |

### Model Storage

The pipeline downloads models to the HuggingFace cache directory on first use:

| Model | Disk Size | Download Trigger |
|---|---|---|
| `openai/whisper-medium.en` | 1.5 GB | First English transcription |
| `openai/whisper-medium` | 1.5 GB | First non-English transcription |
| `htdemucs` | 80 MB | First Demucs run |
| `htdemucs_ft` | 80 MB | First run with `--demucs-model htdemucs_ft` |
| Silero VAD | 2 MB | First `--vad` run |

**Total cold-start footprint:** approximately 5 GB download, 8 GB working disk.

Models can be pre-staged at `C:\SenseVoiceModels\` to avoid re-downloading on multiple machines.

---

## Performance Characteristics

Measured on RTX 3060 12 GB with `openai/whisper-medium.en`:

| Scenario | Pipeline Configuration | Wall Time (per 60 s audio) |
|---|---|---|
| Clean speech, single speaker | `--no-sep --vad` | 5 s |
| Clean speech, full pipeline | default | 30 s |
| Multi-speaker podcast | `--vad --diarize --num-speakers 2` | 60 s |
| Rap with heavy music | `--vad --demucs-model htdemucs_ft` | 90 s |
| 5-minute VOD | default | 150 s |

CPU-only mode is 5–10× slower. `--no-temperature` saves approximately 10% on greedy-decodable content.

---

## Model Selection

The pipeline accepts any HuggingFace Whisper model via the `--whisper-model` flag. For the user's RTX 3060 12 GB, the following models are validated:

| Model | Parameters | VRAM | Speed vs medium.en | Best For |
|---|---|---|---|---|
| `openai/whisper-small` | 244 M | 2 GB | 1.5× faster | Drafts, very long VODs |
| `openai/whisper-medium.en` *(default)* | 769 M | 5 GB | 1× | English general-purpose |
| `openai/whisper-medium` | 769 M | 5 GB | 1× | Multilingual (en/ru/de/fr/es/zh/ja/ko/it/pt/pl/tr) |
| `openai/whisper-large-v3` | 1.55 B | 10 GB | 0.5× | Highest quality; significant gain on CJK languages |
| `distil-whisper/distil-large-v3` (`--fast`) | 809 M | 5 GB | 6× faster than large-v3 | Long-form fast previews |
| `whisper_ft_en_ru` (FLEURS LoRA, custom) | 244 M + adapter | 2 GB | 1.5× faster | Domain-specific finetune |

### Selection Heuristics

- **Default (`medium.en` for English, `medium` for other languages):** Best balance of quality, speed, and VRAM usage.
- **`large-v3`:** Required for highest accuracy on Chinese/Japanese/Korean (~50% WER reduction vs `medium`). For English, the gain over `medium.en` is small (~5%) unless the audio is heavily accented or noisy.
- **`--fast`:** Use for very long VODs (>30 min) where iteration speed matters. Quality is ~5% below `large-v3`.
- **FLEURS LoRA (`whisper_ft_en_ru`):** Use for domain-specific content where `medium.en` produces errors on jargon.

### Switching Models at Runtime

```bash
# Best quality English
WHISPER_MODEL=openai/whisper-large-v3 python transcriber.py input.mp4 --lang en

# Best quality multilingual
WHISPER_MODEL=openai/whisper-large-v3 python transcriber.py input.mp4 --lang zh

# Fast preview
python transcriber.py input.mp4 --lang en --fast
```

---

## Music-vs-Speech Region Analysis

When Demucs is enabled, the pipeline analyses the per-stem RMS energy to identify music-only vs speech-only vs mixed vs silent regions of the input. This produces a `music_regions.json` file in the output directory:

```json
[
  {"start": 0.0, "end": 10.0, "type": "speech"},
  {"start": 10.0, "end": 25.0, "type": "music"},
  {"start": 25.0, "end": 35.0, "type": "speech"},
  {"start": 35.0, "end": 40.0, "type": "silence"}
]
```

This is exported for downstream consumers (e.g. subtitle editors that want to mute captions during instrumental sections). It is informational only and does not affect the current transcription pass.

---

## Chapter Detection

The pipeline can detect natural chapter breaks from pauses in speech. When `--chapters` is enabled, the system groups VAD-detected speech segments into chapters, where each chapter is bounded by silence gaps of at least 3 seconds. Chapters shorter than 15 seconds are absorbed into the previous chapter to avoid noise.

Three output formats are produced:

1. **`chapters.json`** — structured data with start/end times, duration, title, and full text per chapter
2. **`chapters.md`** — human-readable Markdown with title, time range, and excerpt per chapter
3. **`chapters_youtube.txt`** — YouTube-compatible chapter markers in the format `M:SS Title` (or `H:MM:SS Title` for >1 hour content)

By default, chapter titles are derived from the first sentence of the chapter's transcript. With `--chapter-llm`, GPT-4o-mini is used to generate concise 3-7 word titles that better summarize the topic. The LLM path requires the `OPENAI_API_KEY` environment variable.

Example output (`chapters.json`):

```json
[
  {"index": 0, "start_s": 0.0, "end_s": 142.5, "duration_s": 142.5,
   "title": "Introduction to project goals", "n_chunks": 8, "text": "..."},
  {"index": 1, "start_s": 146.2, "end_s": 308.7, "duration_s": 162.5,
   "title": "Technical implementation details", "n_chunks": 9, "text": "..."}
]
```

This is useful for long-form content like podcasts, interviews, lectures, and streamer VODs where viewers want to navigate to specific topics.

---

## JSONL Streaming Output

The pipeline supports real-time streaming of transcription events to a JSONL (JSON Lines) file. When `--jsonl FILE` is specified, the following events are appended to `FILE` as transcription progresses:

| Event | When | Fields |
|---|---|---|
| `start` | Pipeline begins | `file`, `lang`, `model`, `timestamp` |
| `chunk` | Each chunk is transcribed | `text`, `timestamp` (start/end in seconds), `seg_idx` (VAD mode only), `seg_kind` (vad/long-form) |
| `done` | Pipeline finishes | `elapsed_s`, `n_words`, `output_dir` |

Each line is a valid JSON object. Consumers can `tail -f FILE | jq` to watch transcription progress, or pipe to a database, websocket, or chat bot for real-time display.

Example consumer (Node.js):

```javascript
const fs = require('fs');
const readline = require('readline');
const rl = readline.createInterface(fs.createReadStream('transcript.jsonl', {flags: 'r'}));
rl.on('line', (line) => {
  const event = JSON.parse(line);
  if (event.event === 'chunk') {
    console.log(`[${event.timestamp[0]}s] ${event.text}`);
  }
});
```

---

## Accuracy Characteristics

Word Error Rate (WER) measured against Whisper `medium.en` transcribing the same audio on the raw mix (upper bound). For test methodology and ground-truth references, see `audio/TRANSCRIBER_QUALITY_AUDIT.md`.

### Real-World Test Corpus (8 clips)

| Test Clip | Audio Type | WER vs medium.en oracle |
|---|---|---|
| easy_goggins | clean motivational speech, 71 s | 19.9% |
| kohli_interview | single-speaker interview, 60 s | 17.3% |
| podcast_bbc | two-host BBC podcast, 60 s | 15.6% |
| phone_call | 8 kHz phone-quality sales call, 60 s | 20.3% |
| boston_accent | thick accent sample, 30 s | 25.3% |
| australian | accented news interview, 60 s | 24.9% |
| russian_speech | Russian-language speech, 30 s | 14.9% |
| hard_rappers | rap with ad-libs and heavy background music, 60 s | 46.7% |

### Synthetic TTS Test Corpus (14 clips)

Generated via `edge-tts` for reproducible accuracy measurement:

| Test Clip | Language | Metric | Score |
|---|---|---|---|
| gen_whisper_en | en | WER | 0.00% |
| gen_fast_en | en | WER | 2.84% |
| gen_numbers_en | en | WER | 0.00% |
| gen_technical_en | en | WER | 0.00% |
| gen_child_en | en | WER | 0.00% |
| gen_poetry_en | en | WER | 3.79% |
| gen_long_en | en | WER | 0.00% |
| gen_finance_en | en | WER | 16.41% |
| gen_news_de | de | WER | 0.00% |
| gen_news_fr | fr | WER | 0.00% |
| gen_news_zh | zh | CER | 0.00% |
| gen_news_ja | ja | CER | 0.00% |
| gen_spanish_es | es | WER | 0.00% |
| gen_korean_ko | ko | CER | 0.00% |

**Summary:** 13 of 14 synthetic scenarios pass at ≤10% WER. The remaining weakness is finance/numbers-heavy content where Whisper occasionally drops the words "dollars" and "percent".

### Known Accuracy Limits

- **Rap with heavy background music** is fundamentally limited by Demucs's vocal separation ceiling, not by Whisper accuracy. Even oracle transcriptions of the raw mix do not reach ≤2% WER on this content. To improve further would require large-v3 plus rap-specific training data.
- **Russian, Chinese, Japanese, Korean** use `medium` multilingual Whisper because no language-specific variant exists in the medium size class. Large-v3 reduces WER on these by approximately 50%.
- **Number and currency tokens** are sometimes dropped or normalized inconsistently. The `--llm-correct` flag mitigates this through GPT-4o-mini post-processing.

---

## Command-Line Interface

```
python transcriber.py INPUT [flags]
```

| Flag | Default | Description |
|---|---|---|
| `INPUT` | required | Path to audio or video file |
| `--lang` | auto | Language hint: `en`, `ru`, `fr`, `de`, `es`, `zh`, `ja`, `ko`, `it`, `pt`, `pl`, `tr` |
| `--no-sep` | off | Skip Demucs vocal separation |
| `--long-form` | auto for >30 s | Force chunked transcription with timestamps |
| `--vad` | off | Use Silero VAD to skip silence and music-only sections |
| `--auto` | off | Auto-detect audio profile and choose best settings |
| `--diarize` | off | Use Resemblyzer to identify speakers |
| `--num-speakers N` | auto | Number of speakers for diarization |
| `--demucs-model` | `htdemucs` | `htdemucs`, `htdemucs_ft`, `htdemucs_6s`, `hdemucs_mmi` |
| `--whisper-model` | `openai/whisper-medium.en` | Any HuggingFace Whisper model |
| `--out-dir` | `output/` | Output directory |
| `--normalize` | off | Apply EBU R128 loudness normalization |
| `--word-level` | off | Emit `subtitles_word.srt` with per-word timing |
| `--force` | off | Force re-processing, ignore cache |
| `--no-temperature` | off | Disable temperature fallback |
| `--llm-correct` | off | Pass transcript through GPT-4o-mini for cleanup |
| `--multi-pass` | off | Run 3 decoding passes and vote on best result (~20% slower) |
| `--fast` | off | Use `distil-whisper/distil-large-v3` for 6× faster inference |
| `--jsonl FILE` | off | Stream chunks as JSONL (start, chunk, done events) to FILE for real-time consumers |
| `--chapters` | off | Detect chapter breaks from silences (≥3 s gap) and export `chapters.json`, `chapters.md`, `chapters_youtube.txt` |
| `--chapter-llm` | off | Use GPT-4o-mini to generate 3-7 word chapter titles (needs `OPENAI_API_KEY`, with `--chapters`) |

The pipeline reads `WHISPER_MODEL` from the environment if `--whisper-model` is not supplied.

---

## Output Files

For each input file, the pipeline writes the following to `output/<input_stem>/`:

| File | Purpose |
|---|---|
| `transcript.txt` | Clean plain-text transcript |
| `transcript.json` | Full metadata: chunks, VAD segments, speaker labels, configuration |
| `subtitles.srt` | SRT with sentence-aware grouping (max 84 chars / 6 s per block) |
| `subtitles.vtt` | WebVTT (browser-friendly) |
| `subtitles.ass` | Advanced SubStation Alpha (video editor compatible) |
| `subtitles_word.srt` | Word-level SRT, only when `--word-level` is set |
| `report.md` | Markdown summary: config, statistics, transcript preview |
| `_cache_meta.json` | Cache key for fast re-run skip |
| `demucs/` | Separated stems: `vocals.wav`, `drums.wav`, `bass.wav`, `other.wav` |

UTF-8 encoding is used throughout. Cyrillic, CJK, and other non-Latin scripts are preserved.

---

## Caching Behavior

The pipeline writes a cache key to `output/<stem>/_cache_meta.json` after every successful run. The cache key is a hash of:

- file content signature (path + first 1 MB + size)
- Whisper model identifier
- Demucs model identifier
- `--vad` flag
- `--diarize` flag
- language hint
- `--word-level` flag
- `--multi-pass` flag

On the next run with identical inputs, the pipeline returns instantly (≈ 0 s) using the cached `transcript.txt`. Use `--force` to invalidate.

---

## Integration Roadmap

The pipeline currently runs as a standalone CLI tool. Native integration into the Beetle Studio editor is planned:

| Milestone | Target Version | Scope |
|---|---|---|
| Background transcription queue | v3.5.0 | C++ wrapper calls the Python pipeline via subprocess; UI surfaces progress in **Inspector → Audio** |
| Inline transcript display on timeline | v3.6.0 | Subtitle clips rendered as overlay in the timeline viewport |
| Speaker-colored transcripts | v3.6.0 | Use `--diarize` results to color-code speaker turns |
| Editable transcript in inspector | v3.7.0 | User-edited transcripts supersede the automated output |

Until native integration, the recommended workflow is:
1. Run `python transcriber.py input.mp4 --vad --diarize` from the command line
2. Drag the generated `subtitles.srt` onto the Beetle Studio timeline as a subtitle clip

---

## References

- OpenAI Whisper — [https://openai.com/research/whisper](https://openai.com/research/whisper)
- Facebook Demucs — [https://github.com/facebookresearch/demucs](https://github.com/facebookresearch/demucs)
- Silero VAD — [https://github.com/snakers4/silero-vad](https://github.com/snakers4/silero-vad)
- Resemblyzer — [https://github.com/resemble-ai/Resemblyzer](https://github.com/resemble-ai/Resemblyzer)
- HuggingFace Transformers — [https://huggingface.co/docs/transformers](https://huggingface.co/docs/transformers)
- Related internal documents:
  - [`audio/VST_SDK_INTEGRATION.md`](./VST_SDK_INTEGRATION.md) — VST hosting architecture
  - [`engineering/ARCHITECTURE_OVERVIEW.md`](../engineering/ARCHITECTURE_OVERVIEW.md) — system architecture
  - [`engineering/TECHNICAL_STANDARDS.md`](../engineering/TECHNICAL_STANDARDS.md) — coding standards
  - [`engineering/TEST_STRATEGY.md`](../engineering/TEST_STRATEGY.md) — testing methodology
- ISO/IEC 12207:2017 §6.1 — interface specifications
- ISO/IEC 25010:2023 — software product quality model
- ISO/IEC 25023:2023 — quality measurement

---

## Version History

### Change Log

| Version | Date | Author | Change |
|---|---|---|---|
| 1.3.0 | June 2026 | Ryan Foster | Added `--chapters` flag (silence-based chapter detection with optional GPT-4o-mini titles; exports JSON, Markdown, and YouTube-format files). Added `--jsonl FILE` flag for real-time JSONL streaming of transcription events (start, chunk, done) to consumers. Added `--chapter-llm` flag for LLM-generated chapter titles. |
| 1.2.0 | June 2026 | Ryan Foster | Added Whisper large-v3 (1.55 B) and distil-large-v3 as opt-in model options. Added music-vs-speech region analysis using Demucs stem energy. Multi-signal hallucination detector with confidence scores (10 signals: phrase, repeat, logprob, audio RMS, words/sec, etc.). Improved sentence boundary detection (more abbreviations, multi-language). Number/currency formatting in cleanup. |
| 1.1.0 | June 2026 | Ryan Foster | Added `--multi-pass` decoding (3 temperatures, vote on best), `--fast` for distil-whisper, BBC-standard reading-speed constraint (21 chars/sec), expanded SFX tag detection (50+ patterns), cache key extended for multi-pass. |
| 1.0.0 | June 2026 | Ryan Foster | Initial document. Pipeline at v3.4.0-milestone; 8 real-world + 14 synthetic test scenarios documented; medium.en is default Whisper model. |

### Review Cadence

- **Next review:** December 2026
- **Reviewer:** Kirk Beka (CTO)
- **Cadence:** Semiannual, or on any change to the pipeline's external interface (new CLI flags, new output files, new dependencies).