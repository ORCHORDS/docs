# github-actions-self-hosted

**Issue:** Running GitHub Actions on self-hosted runners for private network access and cost control
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
GitHub-hosted runners cannot reach private VPCs, have limited CPU/memory, and cost money at scale. Self-hosted runners solve all three but introduce management overhead.

## Pattern / Solution
Register a self-hosted runner:
```bash
# On the runner machine
mkdir actions-runner && cd actions-runner
curl -o actions-runner-linux-x64.tar.gz -L \
  https://github.com/actions/runner/releases/download/v2.317.0/actions-runner-linux-x64-2.317.0.tar.gz
tar xzf ./actions-runner-linux-x64.tar.gz

./config.sh \
  --url https://github.com/myorg \
  --token $RUNNER_TOKEN \
  --labels self-hosted,linux,x64,production \
  --runnergroup production-runners

sudo ./svc.sh install
sudo ./svc.sh start
```

Kubernetes-based runners with Actions Runner Controller (ARC):
```bash
helm repo add actions-runner-controller \
  https://actions-runner-controller.github.io/actions-runner-controller
helm upgrade --install arc \
  actions-runner-controller/actions-runner-controller \
  -n arc-system --create-namespace \
  --set authSecret.create=true \
  --set authSecret.github_token=$GITHUB_TOKEN
```

```yaml
# runner-deployment.yaml
apiVersion: actions.summerwind.dev/v1alpha1
kind: RunnerDeployment
metadata:
  name: myorg-runners
  namespace: arc-system
spec:
  replicas: 3
  template:
    spec:
      organization: myorg
      labels: [self-hosted, linux, k8s]
      resources:
        requests:
          cpu: 500m
          memory: 1Gi
```

Workflow targeting self-hosted runners:
```yaml
jobs:
  deploy:
    runs-on: [self-hosted, linux, production]
    steps:
      - uses: actions/checkout@v4
      - name: Deploy
        run: helm upgrade --install myapp ./chart
```

## Gotchas
- Self-hosted runners should not be used for public repos — untrusted PRs can execute arbitrary code on the runner
- Runners inherit the IAM role / service account of the host — scope permissions carefully
- ARC auto-scales to zero but cold-start latency (pod scheduling + image pull) adds 1-2 minutes
- Ephemeral runners (`--ephemeral` flag) register for a single job then deregister — prevents state leakage between jobs
- Runner token expires in 1 hour; use registration tokens from the API for automated setup, not the UI token

## Related
- `gitlab-ci-patterns.md`
- `circleci-config-patterns.md`
- `jenkins-pipeline-patterns.md`
