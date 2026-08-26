# actions-job-summaries-annotations-reporting

**Issue:** CI pipelines generate hundreds of megabytes of log text, and the only people who can extract signal from them are the engineers who wrote the pipeline. Test results, coverage deltas, bundle-size regressions, and security warnings get buried inside expandable log groups that nobody opens unless something is already on fire. GitHub Actions has two first-class reporting surfaces that most repos underuse: job summaries (the markdown panel rendered above the log on the run summary page) and annotations (the `::error`/`::warning`/`::notice` lines that surface inline in the PR Files changed view and the run annotations tab). Emitting structured output to these surfaces turns CI from a pass/fail black box into a readable report that reviewers, triagers, and on-call engineers can consume in seconds, without scraping logs or clicking into twenty collapsed steps.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## How job summaries work

1. **Append via the environment variable.** The runner exposes the path to a per-step summary file in the `GITHUB_STEP_SUMMARY` environment variable. Appending markdown with `echo "### Test results" >> "$GITHUB_STEP_SUMMARY"` in bash, or the equivalent redirect in PowerShell, adds a rendered block to the run summary page. GitHub-flavored markdown is supported, so tables, lists, and collapsible details sections all render.
2. **One file per step, grouped per job.** Each step gets its own unique summary file, which means one step's malformed markdown cannot break another step's output. When the job finishes, the runner groups all step summaries into a single job summary; summaries from multiple jobs are ordered by job completion time on the run page.
3. **Overwrite with a single redirect.** Switching from `>>` to `>` in bash replaces that step's summary content instead of appending, which is what you want when a later step reformats an earlier raw report into a final table. Deleting the file entirely removes the step's summary from the page.
4. **Respect the platform limits.** Each step is capped at 1 MiB of summary content; exceeding the cap fails that step's summary upload and produces an error annotation, though the step and job status are unaffected. At most 20 job summaries are displayed per job, so generate a consolidated report rather than a summary per parallel shard.
5. **Treat summaries as masked, semi-persistent output.** Secrets are auto-masked in summaries just as in logs, but anything genuinely sensitive should never be written there; the supported way to remove a leaked summary is deleting the whole workflow run. Point summary content at artifacts or reports for full data instead of inlining it.

## Emitting annotations that surface in pull requests

1. **Use the three workflow commands.** `::error`, `::warning`, and `::notice` written to stdout create annotations, mirroring `core.error`, `core.warning`, and `core.notice` in the Actions toolkit. Annotations appear in the run's Annotations tab, on the job graph, and inside the PR Files changed view when the command includes file and line metadata.
2. **Attach location parameters.** The commands accept `file`, `line`, `col`, `endLine`, `endColumn`, and `title` parameters, for example `::error file=src/app.ts,line=42,endLine=48,title=Coverage decreased::This diff lowered coverage by 2.1%`. Location-aware annotations are what make report output actionable from the PR instead of the Actions UI.
3. **Convert tool output to annotations.** Most ecosystems have a bridge that parses reporter output into these commands: `mikepenz/action-junit-report` for JUnit XML, `pyreportjunit`-style scripts for pytest, or `actions-toolkit`'s core functions for custom scripts. Standardizing on one bridge per repo keeps annotation format consistent across jobs.
4. **Cap the noise deliberately.** GitHub displays a bounded set of annotations per run (10 errors and 10 warnings per job in the UI, with the rest counted but hidden). Failures should emit few, precise error annotations and summarize the long tail in the job summary table rather than spamming hundreds of duplicates that get truncated.

## A layered reporting pattern

1. **Errors as annotations, detail as summary.** The rule of thumb: anything that should block or warn a reviewer goes in an annotation with file/line context; anything that explains or contextualizes goes in the summary. A test job should annotate the ten failing tests and link the rest via a summary table sorted by flakiness and duration.
2. **Generate markdown tables from raw reports.** Keep the raw JSON/XML as an uploaded artifact, then add a final reporting step that reads it and writes a summary table — slowest tests, bundle sizes per entry point, dependency counts, coverage per package. The summary becomes the dashboard; the artifact remains the source of truth.
3. **Use summaries for matrix rollups.** Matrix jobs each get their own summary, so a follow-up job that downloads shard artifacts and writes one combined table gives a single readable view over a 20-shard test run, avoiding the 20-summary display cap.
4. **Link, do not inline, large outputs.** Because of the 1 MiB cap and run-page readability, summaries should link to Pages deployments, artifact downloads, or external dashboards for full reports, keeping only headline numbers and deltas inline.

## Pitfalls seen in real repos

1. **Writing after the step completes.** Once a step finishes, its summary is uploaded and immutable; later steps cannot amend it. Repos that try to append from a cleanup step silently lose content — each step must write only its own file.
2. **Assuming PowerShell overwrites like bash.** The documented PowerShell examples append with `>>` across lines; if you need a replace semantic, restructure the step so the entire summary is written in one redirect rather than assuming `>` behaves identically across shells.
3. **Masked-variable confusion.** A secret written into a summary is masked in display but still lands in the summary payload; masking is a display feature, not encryption. Rotate anything sensitive that was echoed into a summary.
4. **Annotations without file context in PRs.** `::error` with no `file`/`line` parameters still shows on the run, but the whole point for reviewers is inline surfacing; always pass location metadata when the tool output has it.
