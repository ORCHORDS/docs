# 12 Factor App Config Store Vs Env Vars

## Scope

This article addresses Factor III of the twelve-factor app methodology: configuration. It explains the principle that configuration must be strictly separated from code, that configuration must be stored in environment variables (with the caveat that values too sensitive for env vars belong in a dedicated config store), and the trade-offs between env vars, config stores, secrets managers, and config files. The discussion covers the original Wiggins-Hoffman formulation, the practical interpretation that has emerged in modern cloud-native systems, and the boundary between "config" (non-secret runtime settings) and "secrets" (credentials, keys, tokens). The article applies to any application that needs to be deployed across multiple environments without code changes.

## Workflow or implementation guidance

The twelve-factor app methodology, published in 2011 by Adam Wiggins and later maintained by the twelve-factor community, defines twelve principles for building SaaS applications. Factor III, "Config", states that an application's configuration—everything that is likely to vary between deploys (database credentials, third-party API keys, per-environment resource limits, feature flags)—must be stored in environment variables, not in the code or in configuration files checked into the repository. The principle is that the same code can be promoted across environments (dev, staging, production) without modification.

The first step in applying the principle is to distinguish config from code. Config is anything that varies by environment; code is anything that is invariant. The rule is simple but the application is not: a database host is config, but a database connection pool size is config; a feature flag's default is code, but its current value is config; a third-party API's endpoint is config, but the request timeout might be code or config depending on whether it varies.

The second step is to choose the config store. The twelve-factor methodology prescribes environment variables because they are language- and OS-agnostic, are easy to change between deploys, and are difficult to accidentally check into source control. In practice, environment variables have known weaknesses: they are visible to any process that can read the process's environment, they have no type system, they have no audit trail, and they are not designed for high-cardinality secrets. Modern systems therefore use a layered approach: environment variables for non-sensitive config, a secrets manager (HashiCorp Vault, AWS Secrets Manager, GCP Secret Manager, Azure Key Vault) for sensitive config, and a config store (Consul, etcd, Spring Cloud Config) for dynamic config that must be reloadable without a restart.

The third step is to design the boundary between env vars and a config store. The rule of thumb is that anything that is "secret" (a password, an API key, a certificate) belongs in a secrets manager, not in an env var. The reason is twofold: secrets managers provide audit logging, rotation, and access control that env vars do not; and secrets in env vars are easily leaked through process listings, error reports, and logs. Anything that is "non-secret runtime config" (a feature flag value, a log level, a connection pool size) can stay in env vars or move to a config store.

The fourth step is to design the application's config-loading code. The application should read config from a single, well-defined source (an env-var reader, a config-store client) and should fail fast if the required config is missing. The application should not have config scattered across the codebase; every config value should be loaded in one place and passed to the code that needs it.

The fifth step is to design the config's lifecycle. Some config is static (it does not change after deployment); some config is dynamic (it must be reloadable). Static config goes in env vars or in build-time configuration. Dynamic config goes in a config store with a documented reload mechanism (a SIGHUP, a periodic poll, a push from the config server). The reload mechanism must be tested: a config change is applied, the application picks it up without a restart, and the new behaviour is correct.

## Controls

Config controls cover the source of truth, the secret-handling discipline, the reload behaviour, and the audit trail. The source of truth: each config value must have one and only one source. The secret-handling discipline: secrets must never appear in env vars that are logged, in error messages, in process listings, or in source control. The reload behaviour: dynamic config must be reloadable, and the reload must be tested. The audit trail: every config change must be logged, with the user, the time, and the old and new values.

Operational controls include the secrets manager's access policy (only the application identity can read its secrets), the config store's access policy (only the application identity can read its config), and the rotation policy (secrets are rotated on a documented schedule, or on demand when compromised).

## Validation evidence

Validation must prove that config is correctly separated from code. The standard test is to deploy the same code artifact (the same Docker image, the same binary) to multiple environments with different config and verify that the application behaves correctly in each. Validation must also prove that secrets are not leaked. The test inspects the application's logs, error messages, and process listings, and asserts that no secret value appears.

Validation must also prove that the config reload works. A test changes a config value in the config store, waits for the application to reload, and asserts that the new behaviour takes effect. The test must also prove the failure mode: the config store is unavailable, and the application continues to function with the last-known config rather than crashing.

## Failure modes and correction

The dominant failure is secrets in env vars leaking. An exception is logged with the environment in the stack trace, and the secret is exposed. The cure is to scrub env vars from logs and error messages, and to use a secrets manager for sensitive values. A second failure is config sprawl. Every service has its own convention for loading config; one reads from env vars, another from a YAML file, another from a database table. The cure is to standardise on a single config-loading pattern and to enforce it.

A third failure is the config store being a single point of failure. The application cannot start because the config store is unavailable. The cure is to cache the last-known config locally and to fall back to the cache when the store is unavailable. A fourth failure is dynamic config being silently not-reloaded. The config changes, but the application continues to use the old value because the reload mechanism is broken. The cure is to monitor the reload behaviour (a metric on reload attempts and successes) and to alert on staleness.

A fifth failure is config values that should be code. The "max retries" is set to 3 in production and 10 in development, even though the application's correctness does not depend on the value. The cure is to move values that are invariant across environments into the code and to keep only the values that genuinely vary in config.

## Limitations

Env vars are simple and effective, but they are not a complete solution for modern systems. They do not scale to high-cardinality secrets, they do not provide audit trails, they do not support dynamic reload without application cooperation, and they cannot be used for secrets that must be encrypted at rest. A secrets manager is a heavier-weight solution but it provides the features that env vars lack. The right answer is usually a layered approach: env vars for non-sensitive static config, a config store for dynamic config, and a secrets manager for secrets.

The twelve-factor methodology also assumes a certain style of deployment (a long-lived application with a defined startup phase). For functions-as-a-service platforms (AWS Lambda, Cloudflare Workers), the "config" is set at deployment time and the application reads it on each invocation; the principles still apply, but the loading mechanism is different.

## Canonical sources

- Adam Wiggins and the twelve-factor community — *The Twelve-Factor App*, with Factor III "Config" defining the original principle: https://12factor.net/config
- Adam Wiggins — *The Twelve-Factor App* (full document), with the broader methodology context: https://12factor.net/
- Cloudflare — *Configuration* guidance for Workers and Durable Objects, applying the principle to the edge runtime
- HashiCorp — *Vault* documentation, and the AWS Secrets Manager / GCP Secret Manager / Azure Key Vault documentation, the practical implementation of the "secret store" half of the principle
