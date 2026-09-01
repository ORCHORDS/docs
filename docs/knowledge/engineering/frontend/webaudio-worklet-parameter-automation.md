# WebAudio AudioWorklet Parameter Automation

## Scope

Authoring `AudioWorkletProcessor` parameter descriptors and driving them from the main thread with the `AudioParam` automation schedule (`setTargetAtTime`, `linearRampToValueAtTime`, `setValueCurveAtTime`) plus per-block in-processor automation reading. Covers `parameterDescriptors`, `k-rate` vs `a-rate`, the `currentValue`/`defaultValue` distinction, `AudioParam` automation semantics (`cancelAndHoldAtTime` included), and message-passing coordination for non-automatable state. Excludes `ScriptProcessorNode` (deprecated), graph topology, and the audio-file decoding pipeline covered elsewhere in this leaf.

## Workflow or implementation guidance

An `AudioWorkletNode` exposes one `AudioParam` per descriptor the processor declares. The descriptor array is static and shapes everything downstream:

```js
class FilterProcessor extends AudioWorkletProcessor {
  static get parameterDescriptors() {
    return [
      { name: 'cutoff', defaultValue: 0.5, minValue: 0, maxValue: 1, automationRate: 'k-rate' },
      { name: 'drive',  defaultValue: 1,   minValue: 0, maxValue: 4, automationRate: 'a-rate' },
    ];
  }
  // ...
}
registerProcessor('filter-processor', FilterProcessor);
```

The rate is the load-bearing choice. `k-rate` gives the processor one value per 128-frame render quantum; `a-rate` gives a full `Float32Array(128)` the processor interpolates or indexes per frame. A-rate costs memory and per-frame reads and only pays for audibly-fast modulation (FM index, sample-accurate envelopes); everything slower than a control gesture belongs at `k-rate`.

Inside `process`, parameters arrive with their automation already evaluated by the host:

```js
process(inputs, outputs, parameters) {
  const output = outputs[0];
  const cutoff = parameters.cutoff;   // Float32Array(1) for k-rate, (128) for a-rate
  const drive = parameters.drive;
  const c = cutoff.length === 1 ? cutoff[0] : null;

  for (let channel = 0; channel < output.length; channel++) {
    const out = output[channel];
    for (let i = 0; i < out.length; i++) {
      const cut = c !== null ? c : cutoff[i];
      out[i] = shape(this.state[channel], inputs[0]?.[channel]?.[i] ?? 0, cut, drive.length === 1 ? drive[0] : drive[i]);
    }
  }
  return true; // keep the processor alive
}
```

Automation is scheduled from the main thread on the node's `parameters` object and evaluated by the audio thread — that is the whole point: no message passing on the sample path:

```js
const params = workletNode.parameters.get('cutoff');
const t0 = ctx.currentTime;

params.setValueAtTime(params.value, t0);
params.linearRampToValueAtTime(0.9, t0 + 0.05);        // 50 ms open
params.setTargetAtTime(0.2, t0 + 0.4, 0.15);           // exponential settle toward 0.2
```

`setTargetAtTime` is the correct primitive for anything physical (filter sweeps, portamento, decay): it approaches the target asymptotically with the given time constant and never formally ends, so chained events after it compute from the asymptote's current value. `linearRampToValueAtTime`/`exponentialRampToValueAtTime` interpolate from the previous event's value to the scheduled one and require a prior anchor (`setValueAtTime`); `exponentialRamp` additionally forbids zero at either endpoint. `setValueCurveAtTime` interpolates through a supplied `Float32Array` over a duration — for envelope shapes too complex for ramps — and overlapping curves throw. `cancelScheduledValues` drops future events; `cancelAndHoldAtTime` drops them and anchors a new `setValueAtTime` at the current interpolated value, which is the primitive for note-off interrupting a ramp mid-flight.

Two clocks, one rule: all schedule times are `AudioContext.currentTime` (audio-thread clock), not `Date.now()`/`performance.now()`. UI gestures convert to context time (`ctx.currentTime + lead`) at schedule time; never precompute wall-clock timestamps.

State that cannot be an `AudioParam` (strings, mode flags, buffer swaps) goes over `port.postMessage`, and the audio thread must treat messages as eventually-applied hints — a message that arrives mid-quantum applies next quantum, so any sample-accurate requirement forces the value into an `AudioParam` instead. Keep `process` allocation-free: any `new Float32Array` in the loop is a dropout factory; preallocate scratch buffers on construction, and remember `process` returning `false` lets the system garbage-collect the processor when its tail is done.

## Controls

- `parameterDescriptors` as the single source of truth for name, range, default, and rate; UI sliders bind directly to the same min/max/default so main thread and audio thread cannot disagree on ranges.
- `k-rate` by default; `a-rate` only where per-frame modulation is audible — the rate is part of the processor's public contract and cannot change after registration.
- Every ramp preceded by an anchor event (`setValueAtTime`) at schedule time; `exponentialRamp` endpoints nonzero; curves non-overlapping.
- `cancelAndHoldAtTime(now)` for interrupt-style gesture overrides instead of `cancelScheduledValues` (which leaves the value at the pre-ramp anchor and jumps).
- No allocations, no `console.log`, no promise callbacks inside `process`; scratch buffers allocated once in the constructor.

## Validation evidence

- Offline automation audit: render with an `OfflineAudioContext`, dump the parameter's effective values per quantum by having the processor write them to a side buffer, and diff against the mathematically expected schedule for ramp, target, curve, and cancel-and-hold cases.
- Interrupt test: schedule a 2 s linear ramp, call `cancelAndHoldAtTime` at 0.5 s, assert the captured values continue from the held value with no discontinuity larger than one quantum's delta.
- Rate-contract test: instantiate the node, assert `parameters.get('drive').automationRate` equals the descriptor's declared rate and that reassigning an incompatible rate throws per spec.
- Dropout soak: run the processor under load (fewer real-time cores, e.g. `ctx = new AudioContext({ latencyHint: 'playback' })` reversed to interactive under CPU throttle) and assert zero `totalTimingViolations` in the context's `getOutputTimestamp`/console dropout markers across a sustained render.

## Failure modes and correction

- Ramps start from an unexpected value: no anchor event — the previous automation (or default) is the starting point. Always `setValueAtTime(current, t)` before ramping.
- `exponentialRampToValueAtTime` throws or produces `NaN`s: a zero or negative endpoint/value. Offset the range (use `0.0001`) or switch to `setTargetAtTime`.
- Parameter changes sound steppy on fast modulation: the param is `k-rate` — either declare `a-rate` and interpolate per frame, or smooth in-processor between quantums.
- UI knob feels disconnected from the sound: knob drag events are calling `setValueAtTime` per frame instead of one `setTargetAtTime` with a small time constant; the target form is both cheaper and click-free.
- Processor stops processing after silence: `process` returned `false` once inputs went silent; return `true` while tails or scheduled automation remain.
- Clicks at note boundaries: hard `setValueAtTime` jumps at quantum boundaries; replace with short (~5–10 ms) `setTargetAtTime` transitions or per-sample interpolation in the processor.

## Limitations

- Automation evaluation granularity is the 128-frame render quantum; sub-quantum precision only exists for `a-rate` params indexed per frame in your own code.
- Parameter descriptors are fixed at processor registration; adding a param means a new processor name and versioned migration for saved graphs.
- `setValueCurveAtTime` curves are immutable once scheduled and cannot be efficiently concatenated; long evolving shapes prefer `setTargetAtTime` chains.
- Message-port state changes are quantum-latency; sample-accurate non-numeric control is not expressible without encoding it as params.
- Cross-context node reuse is impossible (`AudioWorkletNode` is bound to its context); automation schedules do not transfer.

## Canonical sources

- W3C, Web Audio API, `AudioWorkletProcessor` and parameter descriptors: https://www.w3.org/TR/webaudio/#AudioWorkletProcessor
- W3C, Web Audio API, `AudioParam` automation: https://www.w3.org/TR/webaudio/#AudioParam
- MDN, `AudioWorkletNode.parameters`: https://developer.mozilla.org/en-US/docs/Web/API/AudioWorkletNode/parameters
- MDN, `AudioParam.setTargetAtTime`: https://developer.mozilla.org/en-US/docs/Web/API/AudioParam/setTargetAtTime
