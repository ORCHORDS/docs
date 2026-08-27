# Access Termination Review

## Trigger

Run when employment, contractor access, vendor access, or another authorized relationship ends, and periodically to verify termination controls are working.

## Inputs

- Identity and access inventory
- Employment/contract/vendor termination notice
- Privileged-access records
- Remote-access records
- Asset and credential inventories

## Procedure

1. Establish the effective termination time and systems in scope.
2. Disable interactive and federated accounts within the required termination window.
3. Revoke tokens, API keys, certificates, hardware authenticators, sessions, and other credentials associated with the subject.
4. Remove privileged roles, group memberships, delegated access, and remote-access methods.
5. Recover organization-controlled devices, keys, badges, or other security-related property where applicable.
6. Rotate shared secrets if the departing subject had access to them and individual revocation is insufficient.
7. Transfer ownership of business-critical repositories, data, service accounts, queues, and operational resources.
8. Confirm authorized personnel retain necessary access to organizational information formerly controlled by the departing subject.
9. Record any exceptions, owners, deadlines, and residual risk.
10. Preserve evidence of completion.

## Escalation

Escalate immediately if privileged access remains active, credentials cannot be revoked, sensitive assets are not returned, or ownership gaps could disrupt business operations.

## Completion criteria

- All known access paths are disabled or explicitly excepted.
- Credentials and authenticators are revoked.
- Critical ownership is transferred.
- Evidence and exceptions are recorded.

## Source basis

- NIST SP 800-53 Rev. 5 — PS-4 Personnel Termination
- NIST SP 800-53 Rev. 5 — AC-2 Account Management
