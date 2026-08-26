# incident-postmortem-template

## What is an Incident Postmortem?

An incident postmortem is a structured review process conducted after a system failure or security breach to analyze what happened, why it happened, and how to prevent similar incidents. This template provides a standardized approach to incident analysis that focuses on learning rather than assigning blame.

## Timeline

Document the exact sequence of events with timestamps:
- When did the incident first occur?
- What were the initial symptoms?
- When was it detected by monitoring systems?
- What was the response timeline?
- When was the incident fully resolved?
- Include all key milestones and decision points
- Use UTC timestamps for consistency across teams

## Impact Assessment

Measure the consequences of the incident:
- System downtime duration and frequency
- User impact (number of affected users, accessibility issues)
- Financial losses or revenue impact
- Service degradation metrics
- Customer experience disruption
- Regulatory compliance violations
- Data loss or security breaches
- Business continuity implications

## Root Cause Analysis

Identify the fundamental reason for the incident:
- What was the primary failure point?
- Why did the system fail at that specific moment?
- What design or implementation flaw caused the issue?
- Was it a single point of failure?
- Did existing safeguards fail?
- What underlying assumptions were incorrect?

## Contributing Factors

List all elements that contributed to the incident:
- Process failures or gaps in procedures
- Communication breakdowns between teams
- Tool or infrastructure limitations
- Human error or misjudgment
- External dependencies or third-party issues
- Inadequate testing or monitoring coverage
- Documentation gaps or outdated information

## Action Items

Define specific, measurable steps to prevent recurrence:
- Immediate fixes (patches, configuration changes)
- Long-term improvements (process updates, tooling)
- Resource allocation requirements
- Timeline for implementation
- Responsible team owners
- Success metrics and verification methods
- Dependencies on other initiatives

## Lessons Learned

Capture key insights from the incident:
- What did we discover about our systems?
- What processes need improvement?
- What tools or monitoring are missing?
- How can we better prepare for similar incidents?
- What training or knowledge gaps were revealed?
- What cultural changes are needed?

## Blameless Culture

Postmortems should focus on system improvements, not individual accountability:
- Avoid naming individuals or teams in the main report
- Focus on processes, systems, and organizational factors
- Encourage honest reporting
