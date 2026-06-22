> Auto-generated from `Migration.md` in the docs repo.

> Auto-generated from `Migration.md` in the docs repo.

> Auto-generated from `effects/MIGRATION.md` in the docs repo.

> Auto-generated from `docs/effects/MIGRATION.md` in the docs repo.

---
title: "Effects Plugin Migration Guide"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# Effects Plugin Migration Guide

**Project:** Beetle Studio
**Owner:** Daniel Kim (Effects & Compositing Engineer)
**Reviewers:** Kirk Beka (CTO), Alex Chen (UI)
**Version:** 1.0.0
**Last Updated:** June 2026

---

## Overview

This guide covers migrating effects plugins from the v1 API to the v2 API introduced in Beetle Studio 2.0. The v2 API adds GPU-accelerated processing, improved parameter types, and OpenFX compatibility.

---

## Migration from v1 to v2 API

### Breaking Changes

| Area | v1 (Deprecated) | v2 (Current) |
|---|---|---|
| Entry point | EffectPlugin_Init() | BeetleEffect_Register() |
| Processing | CPU-only Process(frame*) | GPU+CPU ProcessFrame(context*) |
| Parameters | AddParam(name, type, default) | DefineParam(ParamDescriptor) |
| Color space | sRGB only | Linear + sRGB + ACEScg |
| Threading | Single-threaded | Thread-safe required |
| Memory | Plugin-managed | Pool allocator from host |

### Parameter Mapping

| v1 Type | v2 Type | Notes |
|---|---|---|
| PARAM_FLOAT | ParamType::Double | Range now uses DoubleDescriptor |
| PARAM_INT | ParamType::Int | Unchanged semantics |
| PARAM_COLOR | ParamType::RGBA | Now includes alpha channel |
| PARAM_BOOL | ParamType::Boolean | Unchanged |
| PARAM_CHOICE | ParamType::Choice | Now supports icons per choice |
| PARAM_STRING | ParamType::String | Max length increased to 4096 |

---

## Step-by-Step Migration

### 1. Update the entry point

`cpp
// v1 (remove)
extern "C" void EffectPlugin_Init(PluginHost* host) { ... }

// v2 (replace with)
extern "C" BeetleStatus BeetleEffect_Register(BeetleEffectHost* host) {
    host->setName("MyEffect");
    host->setVersion(2, 0, 0);
    host->setCategory("Color");
    return BEETLE_OK;
}
`

### 2. Update frame processing

`cpp
// v1 (remove)
void Process(FrameBuffer* input, FrameBuffer* output) { ... }

// v2 (replace with)
BeetleStatus ProcessFrame(BeetleProcessContext* ctx) {
    auto input = ctx->getInput(0);
    auto output = ctx->getOutput();
    // GPU path available via ctx->getGPUContext()
    return BEETLE_OK;
}
`

### 3. Update parameters

`cpp
// v1 (remove)
AddParam("intensity", PARAM_FLOAT, 0.5f);

// v2 (replace with)
ParamDescriptor desc;
desc.name = "intensity";
desc.type = ParamType::Double;
desc.defaultValue = 0.5;
desc.range = {0.0, 1.0};
desc.displayName = "Intensity";
host->defineParam(desc);
`

---

## Migration Checklist

- [ ] Replace EffectPlugin_Init with BeetleEffect_Register
- [ ] Replace Process with ProcessFrame
- [ ] Update all parameter definitions to ParamDescriptor
- [ ] Add thread-safety (no global mutable state)
- [ ] Switch memory allocation to host pool allocator
- [ ] Test in linear color space (not just sRGB)
- [ ] Verify GPU path works (or gracefully falls back to CPU)
- [ ] Update plugin manifest version to 2.0
- [ ] Run the plugin compatibility test suite

---

## Document Maintenance

### Change Log

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0.0 | June 2026 | Daniel Kim | Initial migration guide |