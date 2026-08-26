# Android DeviceLockManager governance

**Issue:** Device-lock APIs for financed or managed devices can materially restrict a person's device. Accidental enrollment, stale policy, or unavailable recovery causes severe harm.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** restricted capability

## Controls and implementation

Use only with documented eligibility, contractual/legal review, strong server authorization, explicit device/account binding, signed replay-resistant commands, staged warnings, offline grace, and human recovery. Audit every state transition and minimize collected device data.

## Verification

Test wrong device/account, replay, offline expiry, clock changes, server outage, paid-off state, factory reset, transfer, appeal/recovery, and unsupported devices.

## Gotchas

This is not a general kiosk or fraud API. A risk score alone must never trigger irreversible locking.

## Sources

- Android Developers, [Device Lock](https://developer.android.com/reference/android/devicelock/DeviceLockManager)
