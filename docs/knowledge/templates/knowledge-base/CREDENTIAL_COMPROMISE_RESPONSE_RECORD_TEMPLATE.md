# Credential Compromise Response Record Template

Use this record when a password, token, key, session, privileged account, or other authenticator is suspected or confirmed compromised. CISA incident-response guidance explicitly includes credential access and compromised administrator accounts among incidents requiring structured response.

## Incident identification
- **Incident ID:** <identifier>
- **Detected:** <date-time>
- **Credential or account class:** <user-admin-service-token-key-session-other>
- **System or service:** <system-or-service>
- **Response owner:** <role>

## Initial assessment
- **Suspected or confirmed:** <suspected-confirmed>
- **Detection source:** <source>
- **Known exposure window:** <start-end-or-unknown>
- **Observed unauthorized activity:** <none-or-summary>
- **Potentially affected systems or data:** <scope>

## Containment actions
| Action | Completed | Evidence |
| --- | --- | --- |
| Disable or restrict affected account/session | <yes-no-not-applicable> | <reference> |
| Revoke exposed tokens or keys | <yes-no-not-applicable> | <reference> |
| Rotate authenticators | <yes-no-not-applicable> | <reference> |
| Preserve relevant logs and evidence | <yes-no> | <reference> |
| Block confirmed malicious access paths | <yes-no-not-applicable> | <reference> |

## Investigation
- **Authentication logs reviewed:** <yes-no>
- **Privilege changes reviewed:** <yes-no>
- **Lateral movement checked:** <yes-no>
- **Data access or exfiltration checked:** <yes-no>
- **Related credentials or sessions assessed:** <yes-no>

## Recovery
- **Replacement credential issued:** <yes-no-not-applicable>
- **Access restored after validation:** <yes-no>
- **Monitoring increased:** <yes-no>
- **User or owner notified:** <yes-no-not-applicable>

## Closure
- **Root cause or likely cause:** <summary>
- **Residual risk:** <summary>
- **Follow-up actions:** <actions-or-reference>
- **Post-incident review required:** <yes-no>

## Reference basis
- CISA, Federal Government Cybersecurity Incident and Vulnerability Response Playbooks: https://www.cisa.gov/news-events/news/federal-government-cybersecurity-incident-and-vulnerability-response-playbooks
- NIST SP 800-61, Computer Security Incident Handling guidance: https://csrc.nist.gov/pubs/sp/800/61/r2/final
