# cis-benchmarks-implementation

**Issue:** Implementing CIS Benchmarks for cloud and server hardening
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
CIS Benchmarks are consensus-developed security configuration guidelines for operating systems, cloud platforms, databases, and applications. They are referenced in PCI DSS, HIPAA, FedRAMP, and ISO 27001 as hardening standards.

## Pattern / Solution
Priority benchmarks for cloud-native organizations:

CIS AWS Foundations Benchmark (Level 1 = all orgs, Level 2 = sensitive):
- Enable CloudTrail in all regions
- Enable MFA for root account (and delete root access keys)
- Enable AWS Config
- Enable Security Hub and GuardDuty
- No public S3 buckets with sensitive data
- Rotate IAM access keys every 90 days
- VPC Flow Logs enabled

CIS Linux (Ubuntu/RHEL) key controls:
- Disable unused filesystems and services
- Configure auditd with CIS-required audit rules
- Restrict sudo access; no passwordless sudo
- SSH: PermitRootLogin no, PasswordAuthentication no, MaxAuthTries 4
- Set password complexity requirements (libpam-pwquality)

CIS Kubernetes:
- RBAC enabled; no wildcard permissions
- Network policies enforced
- Pod security standards (restricted profile)
- Audit logging enabled for kube-apiserver

Automation:
- Use CIS hardened AMIs from AWS Marketplace
- InSpec / Ansible Hardening roles for ongoing compliance
- Run CIS-CAT scanner monthly; track benchmark score over time

```bash
# Example: Check AWS root account MFA (CIS 1.5)
aws iam get-account-summary | jq '.AccountMFAEnabled'
```

## Gotchas
- Level 2 controls can break functionality — test in non-production first
- CIS Benchmarks are updated frequently — pin benchmark version in documentation
- Cloud CIS Benchmarks cover account/service configuration, not OS hardening — both needed
- Some controls have operational impact (e.g., disabling SSH password auth breaks some automation)

## Related
- `nist-800-53-control-families.md`
- `iso-27002-2022-new-controls.md`
- `penetration-testing-scope.md`
