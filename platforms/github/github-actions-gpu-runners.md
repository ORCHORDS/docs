# github-actions-gpu-runners

**Issue:** Running GPU workloads in GitHub Actions using GPU-enabled runners
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
ML model training, CUDA tests, and GPU-accelerated builds require GPU hardware that standard runners do not provide.

## Pattern / Solution
GitHub-hosted GPU runners (available on Enterprise):
```yaml
jobs:
  gpu-test:
    runs-on: gpu-2-t4
    steps:
      - uses: actions/checkout@v4
      - run: nvidia-smi
      - run: python train.py --device cuda
```
Self-hosted GPU runner setup:
```bash
./config.sh --url https://github.com/myorg/myrepo \
            --token TOKEN \
            --labels self-hosted,gpu,cuda-12
./run.sh
```
Reference in workflow:
```yaml
    runs-on: [self-hosted, gpu, cuda-12]
```
Docker with GPU support on self-hosted:
```yaml
      - run: docker run --gpus all nvidia/cuda:12.0-base nvidia-smi
```

## Gotchas
- GitHub-hosted GPU runners are expensive (10-20x per-minute vs standard); use sparingly.
- Self-hosted GPU runners require the NVIDIA container toolkit for Docker GPU access.
- GPU runners are not available in every region; check current availability.
- Ensure CUDA driver version is compatible with your framework requirements.
- Cache model weights (HuggingFace cache) to avoid re-downloading on each run.

## Related
- `github-actions-large-runners.md`
- `github-actions-self-hosted-runners-2026.md`
