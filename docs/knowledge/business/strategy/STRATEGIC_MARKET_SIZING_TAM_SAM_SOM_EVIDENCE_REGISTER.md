# Strategic Market Sizing Tam Sam Som Evidence Register

## Scope

This article describes how to construct a market-sizing register that documents the assumptions behind a total-addressable-market (TAM), serviceable-addressable-market (SAM), and serviceable-obtainable-market (SOM) figure, and how to record the resulting evidence in the appendix of a business plan. The register is a planning aid; it does not validate the underlying market and does not produce a defensible forecast. The article relies on two primary government data sources: the U.S. Census Bureau's Census Business Builder for local and industry context, and the U.S. Bureau of Economic Analysis's industry tables for national, regional, and industry-level economic activity. Both sources are used to anchor the assumptions to official statistics where possible and to make the residual analyst judgment explicit where it is not.

The register separates observations (counts, revenues, populations), transformations (filtering, indexing, growth-rate application), assumptions (price, take-rate, penetration), scenarios (low, base, high), and judgments (which value is reported to decision-makers). The plan appendix can show one number; the register must show how that number was arrived at so the number can be reviewed, updated, and challenged.

The article is intended to be read alongside the leaf's `CENSUS_BUSINESS_BUILDER_MARKET_PLANNING` article, which describes Census Business Builder in more detail, and the leaf's competitive and industry articles. The market-sizing register feeds several other planning artifacts and must reconcile to them rather than exist in isolation.

## Workflow or implementation guidance

Constructing the market-sizing register proceeds in eight steps.

1. **Set the strategic question.** State why the market is being sized, who will use the figure, and what decision it informs. A figure used to choose between two markets is sized differently from a figure used to support a capital raise.
2. **Define TAM in operational terms.** Replace the abstract label with a specific definition: the population or revenue of all plausible buyers of the product or service, in a named geography, over a named time horizon, at a named price band. Freeze the definition before sourcing data.
3. **Define SAM as a filter on TAM.** Document the filter (for example, buyer segment, geography, regulatory regime, distribution channel). Show the size of the filter and the basis for it.
4. **Define SOM as a further filter on SAM.** Document the share that the organization can credibly reach given current capabilities, channel access, brand recognition, and competitor behavior. SOM is the most sensitive number to assumptions and should be the most carefully documented.
5. **Source each figure from primary data where possible.** Prefer the U.S. Census Bureau's Census Business Builder for establishment counts, demographic context, and small-area indicators. Prefer the U.S. Bureau of Economic Analysis's industry tables for value-added, gross output, and compensation by industry. Where primary data is unavailable, document the substitution and its limitation.
6. **Record the source, vintage, and transformation.** For each input record the publisher, the dataset or program, the reference period, the geography, the unit, the access date, and any transformation (inflation adjustment, growth-rate application, currency conversion, reclassification).
7. **Run a low/base/high scenario.** Document three values for each of TAM, SAM, and SOM with the scenario assumptions recorded. The plan appendix may report only the base case; the register must show the range.
8. **Surface the judgments.** For each figure record the analyst judgments that drive the result (for example, the chosen price band or the chosen penetration curve). The judgments are the most likely source of disagreement and must be visible.

The appendix should conclude with a summary that names the strategic question, the definitions, the values in the base case, the range, and the principal risks of mis-sizing. The summary should be readable without recourse to the underlying tables.

## Controls

- **Definitions frozen before data sourcing.** The TAM, SAM, and SOM definitions are written and approved before any data is pulled. Mid-cycle redefinition is treated as an amendment.
- **Primary-source preference.** Where a figure is available from a primary government source (Census Business Builder, BEA industry tables) it should be used rather than a third-party summary. Substitution requires documentation.
- **Vintage recorded.** Every input has an associated reference period. The appendix does not present a current period value as a substitute for the actual vintage.
- **Transformation logged.** Every adjustment (inflation, growth-rate, currency conversion, reclassification) is logged with the method, the parameter, and the source of the parameter.
- **Scenario rule.** At least three scenarios (low, base, high) are run. The base case is reported with the range; the range is not buried in a footnote.
- **Judgment transparency.** The analyst judgments that drive each figure are named and dated. Disagreement with the judgment is recorded, not removed.
- **Cadenced refresh.** The register is reviewed at intervals aligned with the planning cycle. New official data, reclassification, or material market change triggers an off-cycle review.

## Validation evidence

A reviewer should be able to reconstruct the register from the evidence. Useful artifacts include:

- the strategic question, definitions of TAM, SAM, and SOM, and the approving authority;
- the source list with publisher, dataset or program, reference period, geography, unit, and access date;
- the transformation log with method, parameter, and source;
- the low, base, and high values for TAM, SAM, and SOM with scenario assumptions;
- the judgment log with analyst, date, statement, and basis;
- the variance between the prior and current register with cause;
- the challenge log with names, dates, comments, and dispositions;
- the minutes of the market-sizing review with attendees and decisions.

Validation also includes comparison against external checks. The BEA industry tables should be referenced for value-added and gross output, and the Census Business Builder should be referenced for establishment and demographic context. Where the register's figure diverges from the public data without explanation, the divergence is a finding.

## Failure modes and correction

- **Vanity sizing.** The TAM is reported as the entire category regardless of buyer relevance. Correct by tightening the TAM definition to a population or revenue that is plausibly addressable.
- **Vintage mix.** The register mixes current-period values from one source with base-period values from another without flagging the mix. Correct by recording vintage on every input and refusing mixed-vintage reporting.
- **Hidden penetration assumption.** The SOM is the result of an unstated penetration curve. Correct by surfacing the curve as an explicit assumption with a source.
- **Source substitution without record.** A third-party summary replaces a primary source. Correct by logging the substitution and the reason.
- **Range hidden.** Only the base case is reported. Correct by requiring the register to surface the low and high cases at the review.
- **No reconciliation to plan.** The market size does not reconcile to the operating plan, the capital plan, or the headcount plan. Correct by reconciling the register to the plan before approval.
- **Reclassification ignored.** A reclassification of an industry changes the BEA industry table on which the register depends, but the register is not refreshed. Correct by triggering an off-cycle review when an official reclassification is identified.

When any of these conditions is detected, document the variance, name the corrective action, and route it to the appropriate authority. Do not retroactively rewrite the register.

## Limitations

The register does not validate the market. It documents the assumptions and sources behind a figure; the figure may still be wrong. The article relies on the Census Business Builder and the BEA industry tables as primary anchors, but the register can be applied to industries or geographies for which official data is sparse; in those cases the register will be more reliant on analyst judgment and the limitations of the judgment should be acknowledged.

The register does not address the question of who within the SOM will buy, when, and at what price. That is the subject of separate leaf articles on customer segment evidence, channel planning, and pricing. The register also does not address competitor behavior within the SOM; that is the subject of separate leaf articles on competitive analysis. The market-sizing register, customer evidence, channel planning, and competitor analysis are complementary, not redundant.

This article is general planning guidance and not a guarantee of outcomes. It is not a substitute for qualified financial, accounting, or legal advice on a specific transaction or capital decision.

## Canonical sources

- U.S. Census Bureau, *Census Business Builder — Data Tool* (Census Bureau program page): https://www.census.gov/data/data-tools/cbb.html
- U.S. Census Bureau, *Census Business Builder — Resources and Program Information*: https://www.census.gov/programs-surveys/sis/resources/data-tools/business-builder.html
- U.S. Bureau of Economic Analysis, *Interactive Data Application — Industry Data (GDP-by-Industry)*: https://www.bea.gov/itable/gdp-by-industry
- U.S. Small Business Administration, *Plan your business* (general planning guidance anticipating use of public data in market sizing): https://www.sba.gov/business-guide/plan-your-business