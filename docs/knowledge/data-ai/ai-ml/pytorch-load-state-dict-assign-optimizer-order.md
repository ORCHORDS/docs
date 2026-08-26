# PyTorch load_state_dict assign Changes Optimizer Ordering

**Issue:** Loading a state dict with `assign=True` preserves incoming tensor properties and can replace parameter objects, invalidating an optimizer created beforehand.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls
- Choose `assign` deliberately based on whether module or checkpoint tensor properties must win.
- Create the optimizer after assignment-style loading unless the documented swap mechanism is enabled.
- Validate missing/unexpected keys and parameter identity before training resumes.
- Restore optimizer state only after model parameters are final.
- Record checkpoint, model code, PyTorch version, and assign policy.

## Verification
- Compare parameter identities, device, dtype, layout, and optimizer references with assign true/false.
- Resume one training step and confirm intended parameters update.
- Test tied parameters, wrappers, and partial state dictionaries.

## Gotchas
A successful load does not prove an existing optimizer points at current parameters. `requires_grad` follows module semantics.

## Official sources
- [PyTorch Module.load_state_dict](https://docs.pytorch.org/docs/stable/generated/torch.nn.Module.html#torch.nn.Module.load_state_dict)
