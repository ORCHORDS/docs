# Strategic Portfolio Bcg Growth Share Matrix Register

## Scope

This article describes how to maintain a Boston Consulting Group (BCG) growth-share matrix as an evidence-backed register rather than as a portfolio strategy by itself. The BCG growth-share matrix was developed by Bruce Henderson and the Boston Consulting Group in the late 1960s and 1970s and has been widely adopted in corporate strategy practice. The article treats the matrix as a planning aid that helps classify business units by relative market share and market growth, surfacing where each unit sits in the conventional Star, Cash Cow, Question Mark, and Dog quadrants. It does not validate that any particular classification is correct and does not substitute for primary research on market share and growth.

The register records, for each business unit in the portfolio, the relative market share figure, the market growth figure, the source of each, the date, the access path, and the quadrant assignment. The register does not prescribe an action for each quadrant; the action depends on the unit's strategic context, the organization's capabilities, and the available rebalancing rules documented in the leaf's separate BCG rebalance article.

The article is intended to be read alongside the leaf's `STRATEGIC_GROWTH_SHARE_MATRIX_REBALANCE_RULES` article, which documents the conditions under which a unit is invested, harvested, or divested, and alongside the leaf's `STRATEGIC_HORIZON_H1_H2_H3_PORTFOLIO_BALANCE` and `STRATEGIC_PORTFOLIO_BCG_GROWTH_SHARE_MATRIX_REGISTER` articles, which classify the portfolio by horizon and by quadrant respectively.

## Workflow or implementation guidance

Maintaining the matrix register proceeds in seven steps.

1. **Set the strategic question.** State why the matrix is being maintained, who will use it, and what decision it informs. Without this preamble the matrix is decoration rather than a decision input.
2. **Define the market for each unit.** Replace the abstract label "market" with a specific definition: the set of products, customers, geographies, and competitors considered. The market definition determines the share and growth figures.
3. **Compute relative market share.** For each unit, compute the unit's market share relative to the largest competitor (the conventional BCG formula). Record the source (for example, third-party market reports, internal sales data, regulatory filings), the date, and the methodology.
4. **Compute market growth.** For each unit, compute the growth rate of the unit's defined market over a stated period (commonly three to five years). Use a defensible source and document the period.
5. **Plot each unit on the matrix.** Use a consistent scale. Document the quadrant boundaries (the matrix midline is a judgment, not a fact). Where a unit sits close to a boundary, the boundary itself is a finding to address.
6. **Tag each unit with evidence quality.** For each figure, record the source quality (primary government, third-party market report, internal estimate, sponsor estimate). Units whose share or growth figures are based on sponsor estimation are flagged.
7. **Aggregate and reconcile.** The matrix is reconciled to the capital plan, the operating budget, the headcount plan, and any horizon or ambidexterity appendix. Material variance is a finding.

The appendix should conclude with a summary that names the strategic question, the market definitions, the quadrant assignment of each unit, and the principal risks of misclassification. The summary should be readable without recourse to the underlying tables.

## Controls

- **Market definition frozen before computing share.** The market definition is written and approved before any share or growth figure is computed. Mid-cycle redefinition is treated as an amendment.
- **Primary-source preference.** Where a share or growth figure is available from a primary source (government statistics, audited financial filings) it should be used rather than a third-party summary. Substitution requires documentation.
- **Vintage recorded.** Every figure has an associated reference period. The appendix does not present a current-period value as a substitute for the actual vintage.
- **Quadrant boundaries stated.** The midpoint and the boundary lines are stated explicitly. Movement of a boundary mid-cycle is an amendment.
- **Cadenced refresh.** The register is reviewed at intervals aligned with the planning cycle. Material market change triggers off-cycle review.
- **Independent challenge.** A role separate from the sponsor challenges the market definition, the figures, and the quadrant assignment. The challenge is logged with names, dates, and dispositions.

## Validation evidence

A reviewer should be able to reconstruct the matrix from the evidence. Useful artifacts include:

- the strategic question, the market definitions, and the approving authority;
- the relative market share figure for each unit with source, date, and methodology;
- the market growth figure for each unit with source, date, and methodology;
- the quadrant assignment for each unit;
- the evidence quality tag for each figure;
- the variance between prior and current register with cause;
- the challenge log with names, dates, comments, and dispositions;
- the reconciliation to the capital plan, the operating budget, and the headcount plan;
- the minutes of the matrix review with attendees and decisions.

Validation also includes comparison against external checks. Where a public market report indicates materially different share or growth, the divergence is a finding. Where the matrix implies a rebalance but the rebalance rules article does not authorize it, the two artifacts disagree and the disagreement is a finding.

## Failure modes and correction

- **Market definition drift.** The market defined at the start of the cycle widens or narrows mid-cycle to make a unit look better. Correct by freezing the definition and treating redefinition as an amendment.
- **Sponsor-estimated share.** The share figure is set by the sponsor without independent evidence. Correct by requiring the figure to come from a primary or third-party source within a stated horizon.
- **Boundary movement.** A boundary is moved mid-cycle to keep a unit in its preferred quadrant. Correct by stating boundaries up front and treating boundary changes as amendments.
- **Vintage mix.** The register mixes current-period values from one source with base-period values from another without flagging the mix. Correct by recording vintage on every figure and refusing mixed-vintage reporting.
- **Action assumed.** The matrix is presented as if it prescribes action (for example, "all Dogs must be divested"). Correct by separating classification from action and routing action through the rebalance rules article.
- **No plan reconciliation.** The matrix does not reconcile to the capital plan, the operating budget, or the headcount plan. Correct by reconciling before approval.

When any of these conditions is detected, document the variance, name the corrective action, and route it to the appropriate authority. Do not retroactively rewrite the register.

## Limitations

The BCG growth-share matrix is a classification heuristic. It does not produce a defensible forecast of returns and does not validate that any particular portfolio action is correct. The matrix was developed by the Boston Consulting Group and has been widely adopted; its application to specific portfolios requires primary research on market share and growth that the matrix itself does not provide.

The matrix does not address the question of how to act on a classification. That is the subject of the leaf's separate BCG rebalance article, which documents the conditions under which a unit is invested, harvested, or divested. The matrix also does not address the organization's capabilities (that is the capability heatmap article) or the behavioral ambidexterity required to act (that is the ambidexterity article). The three lenses (matrix, rebalance rules, capability heatmap) are complementary, not redundant.

This article is general planning guidance and not a guarantee of outcomes. It is not a substitute for qualified financial, accounting, or legal advice on a specific transaction or capital decision.

## Canonical sources

- U.S. Small Business Administration, *Plan your business* (general planning guidance that anticipates use of portfolio classification in plan appendices): https://www.sba.gov/business-guide/plan-your-business
- U.S. National Institute of Standards and Technology, *Special Publication 800-39, Managing Information Security Risk: Organization, Mission, and Information System View* (March 2011) — applied here as the framing step (intent, risk response strategy, tiers) before the matrix is plotted: https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-39.pdf
- Boston Consulting Group, *The Product Portfolio Matrix* (BCG Perspectives, 1970s). Publisher: Boston Consulting Group. No public stable URL was confirmed at time of writing; cite the publisher and title only.