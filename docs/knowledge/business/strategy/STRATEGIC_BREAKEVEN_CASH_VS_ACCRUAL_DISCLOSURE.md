# Strategic Breakeven Cash Vs Accrual Disclosure

## Scope

This article describes how to disclose the difference between cash-based break-even and accrual-based break-even in a strategic plan, and how to record the assumptions behind each in a planning appendix. It draws on the U.S. Small Business Administration's break-even guidance for the unit and contribution margin structure, and on the Financial Accounting Standards Board's concepts of accrual accounting and matching for the recognition side. The article is a documentation aid; it does not constitute accounting advice and does not substitute for the work of a qualified accountant.

Cash-based break-even answers the question: at what level of sales do cash inflows equal cash outflows over the period? Accrual-based break-even answers the question: at what level of sales do revenues equal expenses in the income statement for the period? The two figures can diverge materially because of timing differences, depreciation and amortization, prepayments, inventory movements, working-capital changes, accrued liabilities, deferred revenue, and the recognition treatment of longer-term contracts. A plan that reports only one figure can mislead decision-makers about the timing of cash need.

The article is intended to be read alongside the leaf's `BREAK_EVEN_ANALYSIS` article, which presents the SBA break-even formula, and the leaf's cash-flow and reserve articles. The cash-vs-accrual distinction is also implicit in the leaf's `CASH_FLOW_FORECASTING` and `CAPITAL_EXPENDITURE_FORECAST` articles, which together with this article form the planning arithmetic for liquidity.

## Workflow or implementation guidance

Building the disclosure proceeds in seven steps.

1. **Set the strategic question.** State why the cash-vs-accrual break-even disclosure is being prepared, who will use it, and what decision it informs. A disclosure used to support a capital raise will be more detailed than a disclosure used in an internal review.
2. **Define the period.** Break-even is period-bound. State the period covered (typically a quarter or a year) and the conditions under which the period boundaries matter (for example, seasonality or contract renewal cycles).
3. **Classify every cost as cash or accrual.** For each line, record whether the cost is recognized in cash in the period (a cash cost) or recognized in the income statement in the period but settled in cash in another period (an accrual item). Hybrid items should be split with a documented method.
4. **Classify every revenue item as cash or accrual.** Same rule. Long-term contracts, subscriptions billed in advance, percentage-of-completion work, and revenue with contingent consideration should be split.
5. **Compute cash break-even.** Use the SBA unit or contribution-margin formula on cash-classified lines only. Report the result with the underlying fixed cash costs, the unit contribution, and the cash-classified variable cost ratio.
6. **Compute accrual break-even.** Apply the same structure to the income-statement classified lines. Add back depreciation, amortization, and other non-cash items as fixed; subtract non-cash revenues as adjustments. Report the result with the same structural fields.
7. **Reconcile the two figures.** Show the bridge from cash break-even to accrual break-even: non-cash depreciation added back, accrual revenue recognized ahead of cash, prepayments, inventory movements, accrued liabilities, deferred revenue, and the working-capital impact. The bridge is the disclosure.

The appendix should conclude with a summary that names the strategic question, the period, the two break-even figures, the principal reconciling items, and the timing risk if sales fall between the two figures. The summary should be readable without recourse to the underlying tables.

## Controls

- **Definitions frozen before classification.** The period, the cash/accrual classification rule, and the hybrid split method are documented and approved before any line is classified. Mid-cycle redefinition is treated as an amendment.
- **Bridge disclosed.** The bridge between cash and accrual break-even is disclosed, not hidden. The reader of the plan appendix should be able to see the reconciling items.
- **Consistent period.** Both figures use the same period. Mixing periods produces a meaningless comparison.
- **Vintage recorded.** Source figures carry the fiscal period and the closing date. A figure from a different fiscal calendar is flagged.
- **Cadenced refresh.** The disclosure is refreshed at intervals aligned with the planning cycle, or after a material change in cost structure, contract mix, or working capital.
- **Independent challenge.** A role separate from the sponsor challenges the classification and the bridge. The challenge is logged with names, dates, and dispositions.

## Validation evidence

A reviewer should be able to reconstruct the disclosure from the evidence. Useful artifacts include:

- the strategic question, the period, the cash/accrual classification rule, and the approving authority;
- the cost classification with source, amount, and method;
- the revenue classification with source, amount, and method;
- the cash break-even calculation with fixed cash costs, unit contribution, and the cash-classified variable cost ratio;
- the accrual break-even calculation with the same structural fields;
- the bridge between the two figures with reconciling items;
- the variance between planned and actual figures at the prior review with cause;
- the challenge log with names, dates, comments, and dispositions;
- the minutes of the disclosure review with attendees and decisions.

Validation also includes comparison to the cash-flow forecast and the income statement. The cash break-even should reconcile to the cash-flow forecast under a stated set of assumptions; the accrual break-even should reconcile to the income statement. Material variance is a finding, not a footnote.

## Failure modes and correction

- **Single-figure disclosure.** The plan reports only one break-even figure. Correct by requiring both to be disclosed, with the bridge.
- **Period mix.** The cash figure uses one period and the accrual figure uses another. Correct by enforcing a single period and refusing mixed-period reporting.
- **Depreciation forgotten.** The accrual figure treats depreciation as a cash cost, inflating the break-even. Correct by separating depreciation and amortization from cash costs in the classification.
- **Hybrid mislabeling.** Items with both cash and accrual components are placed wholly on one side. Correct by requiring split assignment with documented method.
- **Revenue timing ignored.** Subscription or progress-payment revenue is treated as if it were collected in the same period. Correct by separating billed-but-uncollected and collected-but-unearned items in the revenue classification.
- **No reconciliation to other plans.** The break-even disclosure does not reconcile to the cash-flow forecast or the income statement. Correct by reconciling the disclosure to both before approval.
- **Hidden working-capital effect.** The cash figure does not reflect the working-capital impact of higher sales (for example, more receivables or more inventory). Correct by surfacing the working-capital assumption explicitly in the cash break-even.

When any of these conditions is detected, document the variance, name the corrective action, and route it to the appropriate authority. Do not retroactively rewrite the disclosure.

## Limitations

The disclosure is a planning aid. It does not constitute financial statements, does not establish accounting treatment under U.S. GAAP or IFRS, and does not substitute for the work of a qualified accountant. The cash and accrual figures depend on the classification of costs and revenues, which is itself a matter of judgment and accounting policy. The bridge between the two figures depends on assumptions about timing, prepayment behavior, and working-capital management that may not hold.

The article draws on the SBA break-even guidance for the unit and contribution-margin formula and on FASB concepts of accrual accounting and matching as primary sources. The SBA material is general planning guidance aimed at small businesses, not a definitive statement of break-even economics; the FASB concepts are oriented to financial reporting, not to strategic planning. The application of both to a strategic planning disclosure is by adaptation rather than direct prescription.

This article is general planning guidance and not a guarantee of outcomes. It is not a substitute for qualified financial, accounting, or legal advice on a specific transaction or capital decision.

## Canonical sources

- U.S. Small Business Administration, *Break-even point — Plan your business*: https://www.sba.gov/business-guide/plan-your-business/calculate-your-startup-costs/break-even-point
- U.S. Small Business Administration, *Calculate your startup costs — Plan your business*: https://www.sba.gov/business-guide/plan-your-business/calculate-your-startup-costs
- Financial Accounting Standards Board, *Concepts of Financial Reporting (Statement of Financial Accounting Concepts No. 1, 1978) and Accrual and Matching Concepts (Concepts Statements No. 2 and No. 5, 1980 and 1984)* — FASB standards pages accessible from: https://www.fasb.org/page/PageContent?pageId=/projects/recentlycompleted