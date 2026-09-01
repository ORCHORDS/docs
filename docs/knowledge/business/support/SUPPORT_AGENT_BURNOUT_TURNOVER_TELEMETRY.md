# Support Agent Burnout Turnover Telemetry

## Scope

This article governs how the support desk collects and uses telemetry about agent burnout and turnover. Burnout is a pattern of chronic workplace stress that has not been successfully managed; turnover is the departure of agents from the team. Both are operational risks: a team that is burning out produces lower-quality support, and a team that is losing agents cannot meet its SLAs. The scope covers the signals the desk collects, the protections around those signals, and the actions the desk takes when the signals indicate risk.

The discipline follows the psychosocial hazard framework codified in ISO 45003, which extends the occupational health and safety principles of ISO 45001 to mental health at work. The framework identifies the work-environment factors that contribute to burnout: workload, autonomy, reward, community, fairness, and values. The support desk's telemetry captures signals from each of these factors.

## Workflow or implementation guidance

The telemetry workflow begins with a defined signal set. The signal set is small and bounded: workload (cases handled per shift, after-call work time, escalation rate), autonomy (use of discretion in case handling, satisfaction with tool support), reward (compensation benchmarks, recognition events, career progression), community (peer support interactions, manager one-to-one frequency), fairness (case distribution, escalation fairness, performance review distribution), and values (alignment between agent action and organisational policy). Each signal is operationalised in a measurable metric.

Workload signals are collected from the case-management tool. The tool records the case identifier, the channel, the handling time, the after-call work time, the resolution time, the escalation events, and the agent identifier. The signals are aggregated per agent per shift and per team per quarter. The aggregation is presented in a dashboard that surfaces both the team average and the per-agent distribution, so the manager can identify the agents whose workload is highest.

Autonomy and reward signals are collected from a periodic anonymous survey. The survey is short, voluntary, and conducted by a third party. The survey asks the agent to rate their autonomy, their reward, their community, the fairness, and their alignment with the organisation's values. The survey results are aggregated to the team level; the manager does not see individual responses.

Turnover signals are collected from the human resources system. The system records the agent identifier, the departure date, the reason, and the tenure. The signals are presented in a dashboard that surfaces the team's quarterly turnover rate and the median tenure. A turnover rate that exceeds the policy threshold triggers a structural review.

## Controls

Three controls protect the agent. The first is the access regime: the burnout telemetry is accessible to a defined role list that excludes the agents whose data is being collected. The manager has access to the aggregated team view; the agent has access to their own individual view; the human resources partner has access to the turnover view. The second is the aggregation rule: the dashboard never surfaces a single agent's individual responses in a context where the agent could be identified. The third is the survey participation guarantee: the survey is voluntary, and the agent's decision is not shared with the manager.

A separate control protects against the misuse of the telemetry. A manager who retaliates against an agent for raising a burnout signal is committing a defined violation. The organisation's policy names the violation, the reporting channel, and the consequence. The policy is reviewed annually.

## Validation evidence

Validation evidence is collected continuously. The burnout telemetry is reported to the operations lead, the service desk manager, and the human resources partner. The reporting cycle is monthly for the workload and turnover dashboards, quarterly for the survey, and annually for the structural review. The structural review produces a named action list with owners and dates.

## Failure modes and correction

The most common failure is the telemetry being collected but not acted on. The manager receives the dashboard, agrees that the workload is too high, and does not change the staffing. The correction is the structural review with named actions and the operations lead's accountability for the actions.

The second most common failure is the survey being non-anonymous in practice. The third party contracts for anonymity, but the small team size makes individual responses identifiable. The correction is the aggregation rule and the team-size threshold below which the survey is not conducted.

The third most common failure is the manager retaliating against the agent who raised the signal. The correction is the policy naming the violation and the consequence, and the independent reporting channel.

## Limitations

The telemetry discipline assumes that the support desk can act on the signals. Where the desk cannot adjust staffing, workload, or recognition, the telemetry becomes a record of an unmanaged problem. The organisation should confirm that it has the operational levers to act on the signals before it commits to the discipline.

The discipline also assumes that the agent population is large enough for the signals to be aggregated without identifying individuals. Where the team is small, the survey is conducted at the cohort level (across multiple teams) rather than the team level. The discipline should be applied with awareness of the team size.

## Canonical sources

- ISO 45003:2021, Occupational health and safety management — Psychological health and safety at work — Guidelines for managing psychosocial risks (publisher and title only; ISO standards pages return access-controlled responses to automated clients).
- NIST SP 800-53 Rev. 5, System and Services Acquisition control family, https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final
- ENISA, Risk Management Resources, https://www.enisa.europa.eu/topics/risk-management
- W3C, Technical Report publication conventions, https://www.w3.org/TR/