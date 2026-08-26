# ai-copyright-deep-2026

**Issue:** A team trains a model on web-scraped data. The team receives a DMCA takedown notice. The team reads about New York Times v. OpenAI, the AI Action Plan, and EU AI Act training data transparency. The team needs the 2026 reference for AI copyright and training data.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The 5 key 2026 copyright cases

1. **NYT v. OpenAI (filed Dec 2023, ongoing).** Allegation of training on NYT content. Settlement discussions 2025-2026.
2. **Authors Guild v. OpenAI (filed 2023, class certification 2024).** Class of book authors alleging copyright infringement.
3. **Getty Images v. Stability AI (UK and US, 2023-2026).** Image rights in training data.
4. **UMG v. Suno / RIAA v. Udio (2024).** Music rights in training.
5. **Kadrey v. Meta (settled 2025).** Book authors' case against LLaMA training.

## The 5 jurisdictional regimes

1. **US.** Fair use doctrine; "transformative use" defense. "Market dilution" risk. Ongoing litigation.
2. **EU.** TDM (Text and Data Mining) exception under DSM Directive Article 4, with rights-holder opt-out. AI Act Article 53(1)(c) requires rights-holder reservation respect.
3. **UK.** TDM exception for non-commercial research; commercial use requires license.
4. **Japan.** TDM exception under Copyright Act 2018, with rights-holder opt-out via metadata.
5. **China.** No explicit TDM exception; fair use case-by-case.

## The 5 training data requirements (EU AI Act Article 53)

1. **Public training data summary** (sufficiently detailed to identify use).
2. **Rights-holder reservation respect** (e.g., robots.txt `User-agent: GPTBot`, ai.txt, robots-txt.com).
3. **Compliance with EU copyright** (e.g., TDM exception conditions).
4. **Copyright policy** document.
5. **Opt-out mechanism** for rights-holders.

## The 5-step compliance pattern

1. **Maintain training data inventory** with source, license, date, opt-out status.
2. **Respect opt-out signals** (robots.txt User-agent blocks, ai.txt, structured data opt-outs).
3. **Generate Article 53 training data summary** (template available from EU AI Office).
4. **Document copyright policy** and license terms.
5. **Have a take-down response process** for DMCA / rights-holder requests.

## The 5 anti-patterns

1. **"Web scale" scraping without opt-out handling.** Infringing in EU/JP.
2. **No training data inventory.** Cannot respond to rights-holder requests.
3. **Ignoring robots.txt and ai.txt.** Crawl-delay ignored.
4. **No take-down process.** Slow response invites litigation.
5. **Treating all jurisdictions as US fair use.** EU/JP/UK differ.

## The 5 best practices

1. **Use licensed datasets** where possible (Common Crawl with opt-out applied, GitHub licensed code, public domain).
2. **Implement opt-out** via robots.txt, ai.txt, and structured signals.
3. **Maintain audit trail** of training data sources and dates.
4. **Document fair-use analysis** for each major data source.
5. **Engage rights-holders proactively** for high-value content (news, books, music).

## Verification

The tell that AI copyright compliance is real:

- Training data inventory with source, license, date, opt-out status
- robots.txt and ai.txt opt-outs respected during crawling
- Article 53 (EU) or equivalent training data summary public
- Take-down response process documented and tested
- Copyright policy published
- Licensed data preferred over scraped where possible

The tell it isn't:

- "We trained on the open web, no tracking"
- No response to take-down notices
- No training data summary
- Opt-out signals ignored

## Gotchas

- `robots.txt` is a polite request, not a legal block, in most jurisdictions (except EU where it has force for opt-out).
- Some rights-holders register with `robots-txt.com` aggregator; respecting one source catches many.
- Common Crawl respects opt-outs but lags by 1-2 months.
- The 2026 "consent-or-pay" models (e.g., OpenAI content deals) are emerging alternatives.
- Music and image rights are the highest-litigation areas in 2026.

## Source URLs (verified 2026-08-10)

- https://artificialintelligenceact.eu/article/53/
- https://eur-lex.europa.eu/eli/dir/2019/790/oj
- https://www.copyright.gov/ai/
- https://www.gov.uk/government/publications/copyright-and-artificial-intelligence
- https://www.bundestag.de/en/webarchiv/abgeordnete/biografien_19WP/personendaten.formular?wp=19&land_abk=&id=521260-19WP
- https://nytco-assets.nytimes.com/2023/12/NYT_Complaint_Dec2023.pdf
