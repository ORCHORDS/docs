# Kubernetes Pod FQDN hostname limits

**Issue**

Setting a Pod hostname to its FQDN can exceed the Linux hostname limit when namespace, subdomain, and cluster domain are combined.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Validate the complete generated FQDN before admission.
- Use `setHostnameAsFQDN` only for software that requires it.
- Keep naming budgets for workload, namespace, subdomain, and cluster domain.

## Verification

1. Create boundary-length names and verify scheduling/startup.
2. Compare hostname, DNS records, and application identity.
3. Test cluster-domain changes in a disposable environment.

## Gotchas

- DNS name limits and kernel hostname limits differ.
- A pending Pod may surface the failure as an event.
- Shortening only the container name may not help.

## Official source

- [Official documentation](https://kubernetes.io/docs/concepts/services-networking/dns-pod-service/#pod-s-hostname-and-subdomain-fields)
