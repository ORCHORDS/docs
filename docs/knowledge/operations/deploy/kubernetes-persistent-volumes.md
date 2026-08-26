# kubernetes-persistent-volumes

**Issue:** Provisioning, binding, and safely managing persistent storage in Kubernetes
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Stateful workloads (databases, queues, ML model storage) need durable volumes that survive pod restarts. Mis-configured storage leads to data loss or pods stuck in Pending.

## Pattern / Solution
StorageClass with dynamic provisioning:
```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: fast-ssd
provisioner: ebs.csi.aws.com
parameters:
  type: gp3
  iops: "3000"
  throughput: "125"
reclaimPolicy: Retain       # Retain | Delete — use Retain for production
allowVolumeExpansion: true
volumeBindingMode: WaitForFirstConsumer  # avoid cross-AZ scheduling issues
```

PVC in StatefulSet:
```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgres
spec:
  serviceName: postgres
  replicas: 1
  volumeClaimTemplates:
  - metadata:
      name: data
    spec:
      accessModes: [ReadWriteOnce]
      storageClassName: fast-ssd
      resources:
        requests:
          storage: 100Gi
```

Resize a PVC (requires `allowVolumeExpansion: true`):
```bash
kubectl patch pvc data-postgres-0 -p '{"spec":{"resources":{"requests":{"storage":"200Gi"}}}}'
# Then restart the pod to trigger filesystem resize
kubectl rollout restart statefulset/postgres
```

Backup with Velero:
```bash
velero backup create postgres-backup \
  --include-namespaces production \
  --snapshot-volumes \
  --volume-snapshot-locations aws-default
```

## Gotchas
- `reclaimPolicy: Delete` on a StorageClass deletes the underlying volume when the PVC is deleted — only use in ephemeral environments
- `ReadWriteMany` (RWX) requires a shared filesystem like EFS, NFS, or CephFS; EBS/gp3 only supports RWO
- `WaitForFirstConsumer` delays PV provisioning until a pod is scheduled, preventing cross-AZ volumes
- PVC expansion only works for online volumes on some CSI drivers; offline resize may require node detach
- StatefulSet PVC templates cannot be updated; you must delete and recreate the StatefulSet to change storage

## Related
- `kubernetes-config-maps-secrets.md`
- `disaster-recovery-failover.md`
- `database-migration-zero-downtime.md`
