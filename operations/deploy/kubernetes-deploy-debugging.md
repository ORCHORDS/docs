# Kubernetes Deployment Debugging

## Common Deployment Issues

When deploying applications to Kubernetes, several common issues can prevent pods from running properly. Understanding these problems and their solutions is crucial for effective debugging.

## CrashLoopBackOff

The `CrashLoopBackOff` error indicates that a pod's container keeps crashing and restarting repeatedly. This typically occurs due to application startup failures or misconfigurations.

```yaml
# Example deployment with CrashLoopBackOff issue
apiVersion: apps/v1
kind: Deployment
metadata:
  name: app-deployment
spec:
  replicas: 1
  selector:
    matchLabels:
      app: myapp
  template:
    metadata:
      labels:
        app: myapp
    spec:
      containers:
      - name: myapp
        image: nginx:latest
        ports:
        - containerPort: 80
```

To debug this issue, check pod logs and describe the pod:

```bash
kubectl logs <pod-name>
kubectl describe pod <pod-name>
```

## ImagePullBackOff

The `ImagePullBackOff` error occurs when Kubernetes cannot pull the specified container image from the registry. This usually happens due to incorrect image names, missing credentials, or network issues.

```yaml
# Example of problematic image reference
apiVersion: apps/v1
kind: Deployment
metadata:
  name: broken-deployment
spec:
  replicas: 1
  template:
    spec:
      containers:
      - name: app
        image: registry.example.com/myapp:v1.0  # Incorrect registry
```

Common fixes include:
- Verifying the image name and tag
- Checking registry credentials
- Ensuring network connectivity to the registry

```bash
# Check image pull status
kubectl describe pod <pod-name>
# Verify image exists in registry
docker pull registry.example.com/myapp:v1.0
```

## OOMKilled

The `OOMKilled` error occurs when a container exceeds its memory limits and gets terminated by the system. This is a common issue with memory-intensive applications.

```yaml
# Deployment with memory constraints causing OOMKilled
apiVersion: apps/v1
kind: Deployment
metadata:
  name: memory-intensive-app
spec:
  replicas: 1
  template:
    spec:
      containers:
      - name: app
        image: myapp:latest
        resources:
          requests
