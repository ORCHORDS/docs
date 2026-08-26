# GitHub-hosted runner Azure VNET network-policy contract

**Issue:** Connecting GitHub-hosted runners to an Azure VNET is treated as an isolation control by itself, leaving same-VNET inbound access or unrestricted egress that bypasses the intended CI trust boundary.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Boundary

Azure private networking deploys each eligible GitHub-hosted runner's network interface into the configured subnet in the same Azure region. This gives the organization control over VNET policy, but GitHub cannot block inbound connections once the NIC is in the VNET. GitHub does not require inbound connectivity to the runner.

## Controls

- Dedicate subnets to hosted runners and delegate them only through the documented `GitHub.Network/networkSettings` setup.
- Apply a network security group that explicitly denies all inbound connections to runner NICs, including same-VNET defaults.
- Default-deny egress and allow only GitHub Actions control-plane domains plus explicitly approved registries, secret managers, artifact stores, and deployment targets.
- Use GitHub's current domain data from the Meta API; do not rely on the Azure private-networking IP ranges retired on or after July 1, 2026.
- Do not intercept outbound TLS unless a governed custom image installs and trusts the required intermediate certificate.
- Associate the network configuration only with runner groups whose organization and repository access is least privilege.
- Separate untrusted pull-request workloads from release and production-network runner groups.
- Monitor Azure flow logs, DNS logs, NSG changes, GitHub runner-group changes, and unexpected destinations.
- Plan subnet capacity and a separately configured failover VNET where availability requirements justify the current preview feature.

## Verification

From a test job, prove access to every approved dependency and denial of arbitrary internet, metadata, management, and same-VNET listener endpoints. From another VNET workload, attempt inbound connection to the runner and verify denial. Reconcile the runner group, network configuration, subnet delegation, NSG effective rules, routes, DNS policy, and flow logs.

## Gotchas

Private networking does not provide static IP addresses for larger runners; dynamic addresses remain required. macOS larger runners cannot be placed in a runner group that has a network configuration. Network configuration grants reachability, not application authorization—continue to use short-lived workload identity and resource-level policy.

## Official sources

- [GitHub Docs: Azure private networking for GitHub-hosted runners](https://docs.github.com/en/organizations/managing-organization-settings/about-azure-private-networking-for-github-hosted-runners-in-your-organization)
- [GitHub Docs: Configure private networking for hosted runners](https://docs.github.com/en/enterprise-cloud@latest/admin/configuring-settings/configuring-private-networking-for-hosted-compute-products/configuring-private-networking-for-github-hosted-runners-in-your-enterprise)
- [GitHub Docs: Private networking with GitHub-hosted runners](https://docs.github.com/en/enterprise-cloud@latest/actions/concepts/runners/private-networking)
