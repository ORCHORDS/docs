# bastion-host-pattern

**Issue:** Providing secure, auditable SSH access to private resources without exposing them to the internet
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Database servers and internal APIs are accessible only from private subnets. Engineers need shell access for debugging without punching holes in security groups or maintaining per-engineer VPN credentials.

## Pattern / Solution
Use a minimal bastion host (or AWS Session Manager as a bastion replacement) as the single SSH entry point.

**Traditional bastion with SSH agent forwarding:**
```bash
# ~/.ssh/config on engineer's machine
Host bastion.example.com
  User ec2-user
  IdentityFile ~/.ssh/infra-key
  ForwardAgent yes              # forward agent to jump through

Host 10.0.*
  User ec2-user
  ProxyJump bastion.example.com # jump through bastion
  IdentityFile ~/.ssh/infra-key
  StrictHostKeyChecking no      # private IPs change; disable for private ranges only

# Connect directly to a private DB host
ssh 10.0.64.5

# Port-forward to RDS
ssh -L 5432:mydb.cluster.us-east-1.rds.amazonaws.com:5432 bastion.example.com
```

**Bastion hardening (cloud-init / Ansible):**
```bash
# /etc/ssh/sshd_config
PermitRootLogin no
PasswordAuthentication no
AllowGroups ssh-users
MaxSessions 10
ClientAliveInterval 300
ClientAliveCountMax 2

# Log all commands (script-based audit trail)
# /etc/profile.d/audit.sh
export PROMPT_COMMAND='history -a >(logger -t bash -p local6.info)'
```

**AWS Session Manager (preferred — no open port 22):**
```bash
# No SSH port needed; traffic goes through SSM agent
aws ssm start-session --target i-0abc123def456

# Port forwarding via SSM (no bastion needed)
aws ssm start-session \
  --target i-0abc123def456 \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters '{"host":["mydb.rds.amazonaws.com"],"portNumber":["5432"],"localPortNumber":["5432"]}'
```

**SSM required IAM policy (attach to EC2 instance profile):**
```json
{
  "Effect": "Allow",
  "Action": [
    "ssm:UpdateInstanceInformation",
    "ssmmessages:CreateControlChannel",
    "ssmmessages:CreateDataChannel",
    "ssmmessages:OpenControlChannel",
    "ssmmessages:OpenDataChannel"
  ],
  "Resource": "*"
}
```

## Gotchas
- Agent forwarding (`ForwardAgent yes`) exposes your SSH agent socket on the remote host; anyone with root on the bastion can use your keys during the session. Use `ProxyJump` without forwarding where possible.
- Bastion instances must be patched regularly; use the smallest possible AMI and enable automatic patch management.
- Session Manager sessions are logged to CloudWatch Logs and S3 automatically when configured — SSH bastions require explicit audit tooling.
- If using a bastion, restrict its security group to corporate IP ranges only and rotate the host key after any security incident.

## Related
- `vpc-subnet-design.md`
- `network-security-groups.md`
- `secrets-vault-rotation.md`
