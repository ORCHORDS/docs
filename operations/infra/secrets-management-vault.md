# Secrets Management with HashiCorp Vault

## Overview

HashiCorp Vault is a powerful secrets management solution that provides secure storage, distribution, and management of sensitive data. It serves as a central hub for all your secrets, offering dynamic secrets, automatic rotation, and seamless integration with modern infrastructure like Kubernetes.

## Symptom

Common issues when implementing Vault include:
- Secrets not rotating automatically
- Access denied errors due to incorrect policies
- Integration failures with Kubernetes
- Leasing expiration problems
- Missing dynamic secret backends

## Gotchas

Key challenges to avoid:
- Not configuring proper lease durations for dynamic secrets
- Ignoring the importance of secret rotation policies
- Misconfiguring Kubernetes authentication methods
- Forgetting to renew leases before expiration
- Overlooking the need for backup strategies

## Dynamic Secrets

Vault's dynamic secrets feature generates credentials on-demand with automatic cleanup:

```bash
# Enable database secrets engine
vault secrets enable database

# Configure database connection
vault write database/config/mydb \
    plugin_name=postgresql-database-plugin \
    allowed_roles="*" \
    connection_url="postgresql://{{username}}:{{password}}@postgres:5432/mydb?sslmode=disable"

# Create role with dynamic credentials
vault write database/roles/myrole \
    db_name=mydb \
    creation_statements="CREATE ROLE \"{{name}}\" WITH LOGIN PASSWORD '{{password}}' VALID UNTIL '{{expiration}}'; GRANT ALL PRIVILEGES ON TABLES TO \"{{name}}\";" \
    default_ttl="1h" \
    max_ttl="24h"
```

## Leasing and Rotation

Vault provides automatic secret rotation through lease management:

```bash
# Create a secret with 1-hour lease
vault kv put secret/myapp/config username=admin password=secret

# Check lease information
vault lease lookup secret/myapp/config

# Configure automatic rotation for database secrets
vault write database/roles/myrole \
    db_name=mydb \
    creation_statements="..." \
    default_ttl="1h" \
    max_ttl="24h" \
    renewal_period="30m"
```

## Kubernetes Integration

Seamless integration with Kubernetes enables automatic secret injection:

```yaml
# Vault authentication configuration
apiVersion: v1
kind: ServiceAccount
metadata:
  name: vault-auth
  namespace: default

---
apiVersion: rbac.authorization.k8s.io/v
