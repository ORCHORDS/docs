# Cloudflare Ruleset Phase-Order Governance

## Purpose

Cloudflare Ruleset Engine features execute in ordered phases. A rule can observe only the request state and fields available when its phase runs, while a terminating action can prevent later phases from being reached. Cross-phase ordering is therefore an architectural constraint, not an implementation detail.

This article defines governance controls for teams that operate redirects, URL normalization and rewrites, origin selection, Web Application Firewall controls, rate limiting, header transforms, cache rules, snippets, and related Cloudflare features. Its goal is to prevent configurations that are individually valid but collectively incorrect because they assume the wrong execution order.

The authoritative phase list remains Cloudflare documentation. Do not duplicate the complete list into internal standards because the platform can evolve. Instead, record the specific ordering assumptions on which each design depends and revalidate them during significant changes.

## Current context and source status

Cloudflare documents that Ruleset Engine phases execute in the order shown in its phase reference. Several high-level consequences are especially important:

- Dynamic redirects run before URL sanitization and URL rewrites.
- URL sanitization and URL rewrites run before origin controls and the principal WAF and rate-limiting phases.
- Custom WAF rules run before rate-limiting rules.
- Rate limiting runs before managed WAF rules.
- The documented Cloudflare Access application check is a later internal phase.
- Request Header Transform Rules in the late-transform phase run after the documented WAF and Access application-check positions.
- Cache settings and snippets occur later in the request phase sequence.

A terminating action, such as an applicable blocking or challenge action, can stop processing before later phases execute. "Later" therefore means later for requests that continue through the pipeline, not a guarantee that every request reaches that feature.

Cloudflare also marks some phases as being for configuration purposes only. The corresponding configuration is not necessarily executed at the location suggested by the phase row. Treat such entries according to their documentation rather than inferring runtime behavior from the phase name.

Cloudflare's phase reference states that updating Super Bot Fight Mode rulesets through the Rulesets API is no longer supported and may cause unexpected behavior. Do not manage those rulesets through a generic Rulesets API or infrastructure-as-code path unless current Cloudflare documentation explicitly establishes a supported mechanism.

This article intentionally makes no claim about undocumented Workers placement.

## Practical workflow and controls

### 1. Inventory every configuration entry point

Build an inventory across all ways the account or zone can be changed, including:

- Infrastructure-as-code repositories and modules.
- Cloudflare dashboard configuration.
- Direct API clients and automation.
- Account-level rulesets and zone-level rulesets.
- Managed ruleset deployments and overrides.
- Separate repositories owned by security, network, application, or platform teams.
- Emergency or break-glass procedures.

Assign one authoritative management path per entry point wherever possible. If dashboard changes are permitted, define reconciliation and import procedures so they do not silently drift from infrastructure as code.

The inventory should identify scope, phase, owner, deployment mechanism, affected hostnames, and whether the rule can terminate or mutate a request.

### 2. Document phase assumptions with each rule

Every cross-feature design should state:

- The phase in which the rule is configured.
- Which request fields it reads.
- Whether those fields represent the original or already-transformed request.
- Which earlier phases can change those fields.
- Which later phases depend on its output.
- Whether its action can prevent later processing.
- The account or zone scope involved.
- The evidence used to verify the assumption.

For example, a redirect that examines the path must be designed with the knowledge that dynamic redirects precede sanitization and URL rewrites. It cannot assume that a later normalization or rewrite has already modified the value.

Likewise, a WAF rule may evaluate a URL already affected by earlier URL transformation, but it cannot match a request header that is added only by the later Request Header Transform Rules phase.

### 3. Review data dependencies, not just rule syntax

Represent each design as a short dependency chain:

`input field → producing phase → consuming phase → action → later effects`

Reject designs in which the producer occurs after the consumer. When a required value is unavailable at the desired phase, choose an alternative that is supported and observable. Options may include matching an earlier available field, moving the decision to a suitable supported phase, or removing the cross-phase dependency.

Do not infer that two products share state merely because their expressions use similarly named fields. Consult field and product documentation to determine what is available in each phase.

### 4. Govern security ordering explicitly

Security review should account for the documented sequence rather than treating WAF controls as one interchangeable layer.

Custom WAF rules precede rate limiting and managed WAF evaluation. Consequences include:

- A terminating custom rule can prevent a request from reaching later rate-limiting or managed-rule evaluation.
- Rate-limiting behavior must not rely on a decision made only by managed WAF rules.
- An exception or skip design must be reviewed for exactly which later products or rulesets it affects.
- Observed managed-WAF events may exclude traffic terminated earlier.

Reviewers should inspect the Ruleset Engine action documentation for the exact action being proposed. Actions differ in whether they terminate evaluation, skip selected processing, execute another ruleset, or modify request handling. Do not generalize the behavior of one action to another.

### 5. Separate mutation, enforcement, and routing concerns

Classify rules according to their primary role:

- **Redirect:** returns a response or redirects processing based on early request state.
- **Mutation:** normalizes or rewrites request properties.
- **Routing:** selects or modifies origin behavior.
- **Enforcement:** blocks, challenges, skips, or rate-limits traffic.
- **Late transformation:** modifies request headers after the documented security and Access positions.
- **Caching or later execution:** controls cache behavior or runs a later feature such as snippets.

A single business requirement may span several classes, but each phase should have a clear responsibility. Avoid designs in which a late mutation is expected to retroactively change an earlier routing or security decision.

### 6. Deploy through controlled infrastructure as code

For each supported entry point:

1. Import or reconcile the current platform state.
2. Pin ownership to a repository and responsible team.
3. Review generated changes, including deletions and ordering changes.
4. Prevent multiple modules from competing for the same phase entry-point ruleset.
5. Promote changes through a representative non-production zone where feasible.
6. Use narrowly scoped credentials and an approved deployment identity.
7. Record the deployed ruleset and rule identifiers.
8. Reconcile post-deployment state to detect dashboard or API drift.

Infrastructure as code improves repeatability but does not prove runtime behavior. A syntactically valid ruleset can still encode an impossible phase dependency.

### 7. Verify with Trace and logs

Use Cloudflare Trace, where applicable, to examine how representative requests move through configured rules and phases. Complement Trace with available security events, request logs, origin observations, and controlled test responses.

Test a matrix that includes:

- Original and rewritten URL variants.
- Normalized and non-normalized forms.
- Requests that redirect before later phases.
- Requests allowed or terminated by custom WAF rules.
- Requests near rate-limit thresholds.
- Managed WAF matches and exceptions.
- Requests with and without headers expected from late transforms.
- Cache-eligible and cache-bypassed paths.
- Authenticated and unauthenticated Access paths where relevant.

Capture request inputs, expected phase decisions, actual results, timestamps, deployed rule identifiers, and applicable log or Trace references. Redact credentials, session material, and personal data.

## Review checklist

Before approval, confirm that:

- The current Cloudflare phase reference was consulted.
- Every read field exists when the consuming phase executes.
- No rule expects output from a later phase.
- Redirect behavior is tested against the pre-sanitization, pre-rewrite request state.
- URL rewrite effects on origin, WAF, and rate-limiting matches are understood.
- Custom WAF termination effects on later rate limiting and managed WAF are intentional.
- Late-added headers are not inputs to earlier WAF, rate-limit, or Access decisions.
- Account-level and zone-level ownership are both considered.
- Configuration-only phases have not been interpreted as literal runtime positions.
- Actions have been reviewed using current action documentation.
- Super Bot Fight Mode is not being updated through an unsupported Rulesets API path.
- No conclusion relies on undocumented Workers placement.
- Trace or log evidence covers both normal and terminating paths.
- Rollback restores a known ruleset state rather than layering another uncertain change.

## Failure modes

Frequent failures include:

- **Matching a header before it exists.** A WAF or rate-limit rule expects a header added by late request-header transformation.
- **Expecting a sanitized URL in an earlier redirect.** A dynamic redirect assumes that URL normalization or rewriting has already occurred.
- **Assuming later decisions are visible earlier.** An early phase attempts to depend on an Access, managed WAF, cache, or snippet outcome.
- **Overlooking termination.** Reviewers assume all requests reach rate limiting or managed WAF even when a custom WAF action can stop processing.
- **Testing only the final origin request.** Origin logs show the transformed request but do not reveal what an earlier redirect or security phase evaluated.
- **Treating table proximity as data sharing.** Features are assumed to exchange outputs without documentation.
- **Ignoring account and zone composition.** A locally correct zone rule conflicts with an account-level deployment.
- **Allowing multiple configuration authorities.** IaC, dashboards, and ad hoc API scripts overwrite or reorder one another.
- **Treating configuration-only phases as execution points.** Architecture is based on an ordering implication Cloudflare explicitly does not make.
- **Copying an old phase list into a runbook.** Platform documentation changes while internal assumptions remain frozen.
- **Using unsupported SBFM automation.** A generic Rulesets API workflow continues after Cloudflare has withdrawn support for that update path.
- **Claiming undocumented runtime placement.** Operational decisions rely on assumptions about Workers or another feature not established by the cited references.

## Evidence and review

Retain enough evidence to reproduce both the intended configuration and observed behavior:

- Approved architecture or change record.
- Rule-to-phase inventory and dependency analysis.
- Infrastructure-as-code plan and deployment result.
- Account and zone ruleset identifiers.
- Representative Trace results.
- Security-event or request-log references.
- Origin observations where routing or transformation is involved.
- Test cases for terminating and continuing requests.
- Drift-detection results.
- Rollback verification.
- Reviewer acknowledgement of documented phase assumptions.

Re-review ordering assumptions when Cloudflare changes its phase documentation, when a new product is introduced, when rules move between account and zone scope, or when a rule begins reading a field produced elsewhere. Incident reviews should compare the assumed request state at each phase with Trace and log evidence rather than relying only on the final request seen by the origin.

## Sources

- [Cloudflare Ruleset Engine: Phases list](https://developers.cloudflare.com/ruleset-engine/reference/phases-list/)
- [Cloudflare WAF: Phases](https://developers.cloudflare.com/waf/reference/phases/)
- [Cloudflare Ruleset Engine: Actions](https://developers.cloudflare.com/ruleset-engine/rules-language/actions/)

## Scope note

This article summarizes selected ordering consequences rather than reproducing Cloudflare's complete phase list. Cloudflare documentation is the authority for current product behavior, availability, action semantics, and supported configuration methods. Validate assumptions against current documentation and observed platform behavior before production deployment.
