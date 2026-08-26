# mobile-on-device-ai-foundation-models

**Issue:** Both major mobile platforms now ship first-party on-device large language models that third-party apps can call. Apple's Foundation Models framework (iOS 26, WWDC 2025) exposes a roughly 3-billion-parameter model running on the Neural Engine, and Android offers Gemini Nano through AICore and the ML Kit GenAI APIs on supported flagship hardware. Product teams want summarization, smart replies, and natural-language features without paying per-token cloud costs or leaking user content to a server, but naive integration fails in the field: the model is unavailable on most of the installed base, battery and thermals throttle long generations, and structured output arrives malformed without constrained decoding. This article covers how to adopt on-device AI with correct availability gating, hybrid routing, and type-safe output handling.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Platform capability landscape

1. **Apple Foundation Models.** Available on iOS 26 and later on devices with adequate Neural Engine capacity. The API surface is Swift-only: a shared LanguageModelSession, streaming partial output, tool calling, and guided generation that produces typed Swift structs. It runs entirely offline once the OS assets are present, which means latency is predictable and content never leaves the device.
2. **Android Gemini Nano via AICore.** Google serves Nano through AICore and ML Kit GenAI APIs (summarization, proofreading, image description, and newer function-calling previews). Support is limited to Pixel and select flagship silicon, and model binaries are delivered by Google Play system updates, not your APK, so your app size is unaffected but availability varies.
3. **The installed-base problem is the real story.** On-device model coverage across a typical production fleet is well under half of active devices in 2026. Every AI feature needs a deterministic answer for the "model not available" case, which is the majority case for the next several years.
4. **Cross-platform teams need an abstraction.** Capacitor, React Native, and Kotlin Multiplatform apps should wrap platform AI behind one interface (available, generate, stream) so calling code does not branch on OS, with a cloud or no-op fallback selected at runtime.

## Guided generation and structured output

1. **Use guided generation, not raw prompts, for app logic.** Apple's @Generable and @Guide macros constrain decoding to a schema you define, returning validated Swift structures. This is the difference between parsing "maybe JSON" and receiving a typed struct, and it eliminates a whole class of runtime crashes from malformed model output.
2. **Constrain output shape before constraining content.** Define narrow output types (an enum for classification, a small struct for extracted fields). Smaller constrained schemas finish generation faster, which directly reduces on-device latency and battery cost.
3. **Handle refusal and empty results explicitly.** On-device safety filters will decline some inputs. Design API responses so refusal is a first-class outcome the UI can render gracefully, not an exception path.
4. **Keep prompts versioned like code.** Prompt text embedded in shipped binaries cannot be hot-fixed without a release. Ship prompts from your backend (or remote config) keyed by app version so you can iterate without an app update, while keeping an in-bundle default for offline first run.

## Hybrid on-device and cloud routing

1. **Route by task sensitivity first, capability second.** Freeform generation over user content is a natural on-device task because content never leaves the phone; complex reasoning can go to cloud models. Publish a routing matrix so product and security review the same table.
2. **Gate on availability at runtime, not at install.** Query model availability on every feature invocation. Android devices gain or lose Nano access with Play system updates, and iOS devices vary by hardware; a cached capability check goes stale.
3. **Degrade gracefully down a fallback chain.** Preferred order for consumer features: on-device model, then a smaller cloud model, then a non-AI heuristic, then a clear "not available" state. Never let a missing model break the core flow the AI was decorating.
4. **Instrument which tier served each request.** Log route taken, latency, and token counts (server-side costs differ by orders of magnitude between tiers) so you can measure whether the on-device tier is actually absorbing the load you predicted.

## Battery, thermals, and performance

1. **Budget generation time like network time.** On-device generation of a few hundred tokens takes seconds, not milliseconds. Show streaming progress, and keep in mind the same thermal throttling that slows games applies to sustained inference.
2. **Prefer many small calls over one huge call.** Chunking summarization or extraction into small guided-generation calls keeps each under thermal budgets, streams earlier, and is cancellable mid-flow when the user navigates away.
3. **Cancel sessions when views disappear.** LanguageModelSession work continues unless cancelled; tie cancellation to view lifecycle the same way you cancel network requests, or generation keeps burning battery in the background of a dead screen.
4. **Test on old hardware.** A feature that feels instant on a flagship can take 5-10x longer on a 4-year-old device that technically supports the framework. Include the oldest supported device in your QA matrix for every AI feature.

## Privacy and safety review

1. **On-device means on-device.** The core privacy win is that prompt content never transits your servers. Preserve it: do not mirror on-device prompts or outputs into analytics beyond coarse metadata, or the privacy story collapses.
2. **Disclose AI features accurately.** App Store review and platform policy require honest description of AI functionality. A summary generated by the on-device model should not be presented as human-written, and consent flows should state where processing happens.
3. **Never feed on-device model output into privileged actions without validation.** Tool calling lets the model invoke functions you register; keep those tools narrowly scoped and validate arguments server-side before any state mutation, exactly as you would validate user input.
