# Ransomware Symptom Support Triage

## Purpose and scope

This procedure helps frontline support recognize and safely route possible ransomware without attempting forensic analysis. Reports may include unreadable files, unfamiliar extensions, ransom notes, mass renaming, disabled security tools, or simultaneous loss of shared data. A single corrupt file is not proof, but credible indicators are time-sensitive because ordinary troubleshooting can spread damage or erase volatile evidence. Negotiation, payment, attribution, eradication, and recovery decisions belong to authorized incident leadership.

## Safe intake

Record the reporter, affected device or service, first observation with time zone, exact wording, extensions, affected shares, and whether others see the behavior. Accept a screenshot through the approved channel when policy permits; never instruct the user to open links, download decryptors, contact the actor, or forward executables. Ask whether activity continues and whether the endpoint connects to shared drives, synchronization services, or removable media. Determine whether essential operations are affected.

Do not restart, power off, run cleanup tools, delete notes, or reconnect a disconnected system unless the incident runbook directs it. These actions can destroy useful state or resume propagation. Do not browse broadly from the suspect endpoint or use it to change passwords.

## Containment workflow

1. Select the security-incident route and page the designated contact through an independently maintained channel.
2. When safe, instruct the user to unplug Ethernet and disable Wi-Fi or cellular networking. Do not ask them to manipulate enterprise network controls beyond their authority.
3. Leave the device powered on but idle unless responders direct otherwise. For cloud, virtual, industrial, or medically relevant systems, defer isolation mechanics to the responsible operator because abrupt action may add harm.
4. Tell the reporter not to use shared credentials, removable media, or synchronized folders from another device until cleared.
5. Send responders observed indicators, scope, timeline, actions already taken, and critical dependencies. Separate facts from guesses.
6. Keep later instructions in the incident channel. Acknowledge affected users without asserting attribution, encryption scope, or data theft before investigation supports it.

## Controls and evidence

The intake form should offer a high-priority ransomware indicator without requiring support to assign final classification. Preserve original timestamps and exact strings. Record who requested isolation, how it was performed, network identifiers, and whether the device remained powered. Restrict screenshots and logs because directory listings and notes may expose confidential information.

Incident responders decide whether to collect memory, disk images, logs, or malware samples. Support validates its work by confirming escalation acknowledgement, known isolation status, safe instructions to the reporter, and attributable subsequent actions. Exercise an offline laptop, a network share, an after-hours report, and an ambiguous corruption event. Measure paging and containment acknowledgement, not merely ticket closure. Review exercises for unsafe canned instructions, inaccessible emergency contacts, and confusion between endpoint isolation and account disablement.

## Failure handling

If security does not acknowledge within the internal emergency threshold, invoke the secondary incident chain rather than waiting in a normal queue. If disconnection is unsafe, advise the user to stop interacting and seek an authorized operator. If symptoms stop, maintain escalation: encryption may have completed or become intermittent. If the event is benign, security can downgrade it without penalizing good-faith reporting.

Never promise backups will restore everything, deny possible exfiltration, or suggest payment ensures recovery. If the user already paid, contacted the actor, installed a tool, or restarted equipment, document this without blame and alert responders. If a suspect system was inadvertently reconnected, record when and how, then notify incident command rather than attempting to hide the mistake. Authorized legal and incident owners decide external notifications and law-enforcement contact.


## Escalation, recovery validation, and failure handling

Escalate for cross-tenant or widespread impact, unclear authority, suspected compromise or exposure, safety concerns, irreversible action, failed rollback, or residual risk outside the service owner’s delegation. Provide identifiers, timeline, evidence locations, containment, attempted actions, unresolved questions, and the decision needed. Support continues coordinated customer communication until technical ownership is acknowledged.

Validate recovery by repeating the original business operation safely, checking durable state at the authoritative system, reviewing error and security telemetry, and testing an unaffected path. Remove temporary access, test artifacts, flags, and exceptions. Document recovered time, residual impact, monitoring interval, acceptance, and corrective owner. A workaround requires a stated risk, expiration, and tracked permanent correction.

When a diagnostic action fails, stop harmful repetition, preserve the exact error and correlation ID, execute rollback, and return to the last safe state. If rollback is unavailable, declare or update the incident. Communicate partial results and missing evidence honestly. Outcomes are limited by architecture, telemetry, retention, connectivity, third-party behavior, and locally tested procedures.

## Limitations, authority, and internal recommendations

**Authoritative guidance** consists only of the cited standards or platform publications within their scope. **Internal recommendations** are this article’s intake fields, approval gates, evidence expectations, routing, and communication checkpoints. Local policy and accountable owners remain controlling. No certification, statutory deadline, universal support, or current compliance claim is made.

## Canonical sources

- CISA StopRansomware Guide: https://www.cisa.gov/stopransomware/ransomware-guide
- NIST SP 800-61 Rev. 2: https://csrc.nist.gov/pubs/sp/800/61/r2/final
