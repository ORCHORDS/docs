# disaster-recovery-failover

**Issue:** Planning and executing disaster recovery failover for production services
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Region outages, data corruption, and catastrophic failures require a tested failover procedure. Without a DR plan, teams improvise under pressure and extend downtime.

## Pattern / Solution
DR tiers (choose per service SLA):
| Tier | RTO | RPO | Pattern |
|------|-----|-----|---------|
| Hot standby | < 5 min | near-zero | Active-active, sync replication |
| Warm standby | 15–30 min | < 15 min | Active-passive, async replication |
| Pilot light | 1–4 hours | 1 hour | Minimal replica, restore from backup |
| Backup & restore | 4–24 hours | 24 hours | Snapshots to S3, restore on incident |

Failover runbook template:
```markdown
## DR Failover: [Service] to [DR Region]

### Pre-conditions
- [ ] Primary region confirmed unhealthy (not a false alarm)
- [ ] Incident bridge open, stakeholders notified
- [ ] DR region health check passing

### Steps
1. Promote DR database replica to primary
   ```bash
   aws rds promote-read-replica --db-instance-identifier myapp-dr
   ```
2. Update Route53 to point to DR load balancer
   ```bash
   aws route53 change-resource-record-sets --hosted-zone-id $ZONE_ID \
     --change-batch file://failover-record-set.json
   ```
3. Verify health endpoint in DR region
   ```bash
   curl https://dr.myapp.example.com/health
   ```
4. Notify stakeholders of failover complete
5. Begin root cause analysis of primary region failure

### Rollback (fail back)
1. Re-sync data from DR back to primary (after primary recovery)
2. Update Route53 back to primary
3. Demote DR replica
```

Test DR regularly:
```bash
# Chaos engineering — terminate primary region instances
aws ec2 terminate-instances --instance-ids $(
  aws ec2 describe-instances \
    --filters "Name=tag:environment,Values=production" \
              "Name=availability-zone,Values=us-east-1a" \
    --query 'Reservations[].Instances[].InstanceId' \
    --output text
)
```

## Gotchas
- RTO/RPO targets are meaningless without a tested runbook — run DR drills quarterly
- DNS TTL at 300s adds 5 minutes to failover even after all other steps complete; set TTL to 60s in advance
- Database promotion is irreversible in some configurations; ensure the original primary is truly failed before promoting
- Application config (env vars, secrets) must exist in the DR region before failover, not during
- Failback is often harder than failover and causes a second outage if not planned

## Related
- `multi-region-deployment.md`
- `rollback-runbook.md`
- `incident-runbook-template.md`
- `on-call-escalation-policy.md`
