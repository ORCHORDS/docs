# ArgoCD GitOps Getting Started Guide

## Overview
Argo CD is a powerful GitOps continuous delivery tool that enables declarative, automated application deployment across Kubernetes clusters. This guide covers essential concepts and practical implementation patterns for modern GitOps workflows.

## App-of-Apps Pattern
The app-of-apps pattern organizes complex deployments by creating a parent application that references multiple child applications. This approach provides better organization, dependency management, and scalability.

```yaml
# apps/parent-application.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: parent-app
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/example/argocd-apps.git
    targetRevision: HEAD
    path: apps
  destination:
    server: https://kubernetes.default.svc
    namespace: default
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

```yaml
# apps/child-application.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: child-app
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/example/argocd-apps.git
    targetRevision: HEAD
    path: apps/child-app
  destination:
    server: https://kubernetes.default.svc
    namespace: default
```

## Sync Waves
Sync waves control the order of application deployment, ensuring dependencies are created before dependent applications. This prevents deployment failures due to missing resources.

```yaml
# apps/database.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: database
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/example/argocd-apps.git
    targetRevision: HEAD
    path: apps/database
  destination:
    server: https://kubernetes.default.svc
    namespace: database
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
  syncWave: -1

# apps/api.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: api
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/example/argocd-apps.git
    targetRevision: HEAD
    path: apps/api
  destination:
    server: https://kubernetes.default.svc
    namespace: api
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
  syncWave
