# Azure Bastion Jumphost Governance

## Purpose

Azure Bastion provides managed RDP and SSH access to virtual machines without exposing public IP addresses. Governance ensures that administrative access flows through Bastion with recorded sessions, that network exposure is minimized, and that administrative credentials are managed centrally.

## Current context and source status

Azure Bastion is generally available. The current SKU tiers (Basic, Standard, Premium) determine feature availability, including session recording, IP-based connection, and Kerberos authentication. Specific SKU features and supported regions evolve; verify the current SKU capabilities for your target region before standardizing on a tier.

## Governance workflow and controls

### 1. Choose SKU

Adopt the SKU that meets the workload's session-recording and authentication requirements. Session recording is not available on the Basic SKU. Kerberos authentication is not available on Basic.

### 2. Deploy to a dedicated subnet

Bastion requires a dedicated subnet named `AzureBastionSubnet` with a `/26` or larger address space. Do not deploy other resources into that subnet.

### 3. Restrict access

Apply network security group (NSG) rules to limit Bastion access to approved source ranges. Where possible, restrict access to a corporate VPN or a privileged access workstation.

### 4. Require session recording

Enable session recording for all administrative sessions to production workloads. Configure the storage account destination with versioning, soft delete, and immutable retention. Restrict access to the recorded sessions.

### 5. Use just-in-time access

Require JIT elevation for VM access through Microsoft Defender for Cloud or PIM. Approvals MUST be recorded.

### 6. Manage credentials

Use Azure Key Vault to store VM credentials. Disable local administrative accounts where possible. Mandate Microsoft Entra authentication for Windows VMs joined to Entra ID.

### 7. Audit usage

Send Bastion diagnostic logs to a central Log Analytics workspace. Alert on unusual patterns: outside-hours access, repeated failed authentications, access from unknown IP ranges.

## Validation and evidence

- Bastion SKU configuration.
- Subnet configuration and NSG rules.
- Session recording storage configuration.
- JIT configuration and approval log.
- Diagnostic log destination and retention.
- Audit alerts configuration.

## Failure correction

Common defects include deployment of Bastion without session recording, public IP exposure on target VMs, and credentials stored in plaintext. Corrective actions include a deployment-time check that fails if Bastion SKU lacks recording, an NSG review that flags public-IP VMs, and a credential-storage scan.

## Limitations

- Azure Bastion is specific to Azure.
- Session recording has storage costs; size the retention accordingly.
- Some VM SKUs are not supported; validate per VM.
- Bastion does not replace identity controls; combine with Conditional Access.

## Canonical sources

- Azure Bastion documentation, current edition.
- Microsoft Defender for Cloud JIT documentation, current edition.
- Azure Architecture Center hub-spoke network topology, current edition.

## Scope note

This article belongs to the platforms leaf and cross-references the security leaf for privileged access, the operations leaf for change windows, and the engineering leaf for remote access patterns.
