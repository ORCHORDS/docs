# k9s-kubernetes-tui

**Issue:** Debugging Kubernetes with kubectl is slow and requires many commands
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Checking pod logs, exec into containers, and watching deployments requires multiple kubectl commands.

## Pattern / Solution
k9s launches TUI for Kubernetes. Navigate resources with keyboard: :pods, :svc, :deploy. l for logs, s for shell exec, d for describe, ctrl-k to kill pod. Filter with /. Works with any kubeconfig context.

## Gotchas
- k9s context follows current kubectl context — switch with :ctx
- Skins and plugins configurable in ~/.config/k9s/config.yaml

## Related
- lazydocker-patterns, github-cli-daily-workflow
