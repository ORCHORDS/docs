# Apple continued processing background task lifecycle

**Issue:** A person starts an export, upload preparation, or on-device analysis and backgrounds the app. Treating it as a scheduled refresh or unlimited background assertion either stops useful work early or consumes resources without system-visible progress and cancellation.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** newer Apple platform API; gate exact availability

## Controls and implementation

Use `BGContinuedProcessingTask` only for documented, user-initiated work that begins while the app is foregrounded and may need minutes after backgrounding. Create a localized request title/subtitle and unique identifier under the registered wildcard. Choose `queue` when later execution remains useful or `fail` when immediate execution is required.

Persist job input, progress, output staging, and an idempotent completion marker before submission. Register the launch handler, report meaningful progress, install the expiration handler immediately, and make cancellation leave recoverable state. Request GPU or other optional resources only after checking `supportedResources` and configuring the required entitlement.

## Verification

Test queue and fail strategies, immediate resource pressure, backgrounding, user cancellation from system UI, expiration, app termination, reboot, duplicate submission, progress updates, unsupported OS, missing entitlement, disk exhaustion, and resume after partial output. Confirm cancellation cannot publish an incomplete artifact.

## Gotchas

Successful request construction or submission does not guarantee execution. The task is not a replacement for silent periodic work, and optional GPU/background inference access has separate capability and entitlement constraints.

## Sources

- Apple Developer, [Performing long-running tasks on iOS and iPadOS](https://developer.apple.com/documentation/backgroundtasks/performing-long-running-tasks-on-ios-and-ipados)
- Apple Developer, [BGTaskScheduler](https://developer.apple.com/documentation/backgroundtasks/bgtaskscheduler)
