# ansible-vault-secrets

**Issue:** Encrypting and managing secrets in Ansible with Vault
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Plaintext passwords and API keys in Ansible variables or inventory files expose credentials in Git. Ansible Vault encrypts secrets at rest while keeping them usable in playbooks.

## Pattern / Solution
Encrypt a single value (inline vault):
```bash
ansible-vault encrypt_string 'supersecretpassword' \
  --name 'db_password' \
  --vault-id production@prompt
```

Output for use in vars file:
```yaml
db_password: !vault |
  $ANSIBLE_VAULT;1.2;AES256;production
  66386439653236336166653235306...
```

Encrypt an entire vars file:
```bash
ansible-vault encrypt group_vars/production/secrets.yml \
  --vault-id production@~/.vault_pass_production

# Edit in place
ansible-vault edit group_vars/production/secrets.yml

# View
ansible-vault view group_vars/production/secrets.yml
```

Vault password file (for CI):
```bash
# Store in a secrets manager; retrieve at runtime
aws secretsmanager get-secret-value \
  --secret-id ansible/vault/production \
  --query SecretString --output text > /tmp/vault_pass

ansible-playbook deploy.yml \
  --vault-password-file /tmp/vault_pass

rm -f /tmp/vault_pass
```

Multiple vault IDs (staging + production):
```yaml
# ansible.cfg
[defaults]
vault_identity_list = staging@~/.vault_pass_staging, production@~/.vault_pass_production
```

## Gotchas
- Vault-encrypted files cannot be `git diff`'d meaningfully; add `.gitattributes` to mark them as binary or use git-crypt instead
- Never commit vault password files; they belong in a secrets manager
- Rotating the vault password requires re-encrypting every vault file: `ansible-vault rekey --new-vault-password-file newpass`
- `ansible-vault encrypt_string` output is whitespace-sensitive; YAML indentation must be exact
- Vault only protects at rest; once decrypted in a playbook, values appear in `ansible-playbook -vvv` output — use `no_log: true` on sensitive tasks

## Related
- `ansible-idempotency-patterns.md`
- `secrets-in-deploy-2026.md`
- `kubernetes-config-maps-secrets.md`
