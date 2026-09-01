# Support Interval Staffing Forecast

Daily staffing totals hide the problem: a support desk does not experience demand by the day, it experiences demand in half-hour or quarter-hour intervals, and a forecast that is right on average can still fail every morning and idle every mid-afternoon. Interval-level forecasting converts historical contact arrivals into expected demand per interval, applies shrinkage, and produces the staffing requirement the schedule must satisfy. This article defines that math and its governance.

## Scope

This article covers interval-level demand forecasting and staffing calculation for support channels: data preparation, the forecast itself, shrinkage and occupancy adjustments, requirement computation, and accuracy tracking. It applies to voice, chat, and ticket queues that are forecast and staffed separately by interval.

It does not cover agent scheduling and shift design (which consumes the requirement this article produces), hiring plans and capacity strategy over quarters, or priority queue routing rules. It assumes historical interval data of reasonable quality exists for at least several weeks; where history is thin, the limitations section applies.

## Workflow or implementation guidance

The method runs as a repeating monthly cycle with weekly refresh:

1. Data preparation. Collect interval counts (30- or 15-minute buckets) per channel from the source systems: offered contacts for synchronous channels, arrivals for tickets. Clean the series: remove or flag days distorted by major incidents, marketing sends, outages, and public holidays; verify timezone alignment; and separate the channels, because their intraday shapes differ (voice peaks early, tickets accumulate through the day).
2. Base week construction. Build a representative week by weekday using a trimmed average (for example, excluding the highest and lowest observations per weekday-interval) so single distortions do not anchor the plan. Apply trend by comparing the same weekdays across recent weeks to detect growth or decay.
3. Interval forecast. Produce expected volume per interval for each future weekday: base volume multiplied by trend, adjusted for known calendar events (holidays, product launches, billing runs) using explicit, documented multipliers rather than silent judgment.
4. Workload conversion. Convert volume to workload: for synchronous channels, multiply expected contacts by average handle time (talk plus after-contact work) per interval; for asynchronous queues, use arrivals multiplied by handling time per item. Handle time is averaged per interval from cleaned history, not from a single month's outlier.
5. Shrinkage. Gross up for time agents are paid but not producing: breaks, training, coaching, meetings, system and login issues, and untracked absence. Shrinkage is applied as a divisor on productive time (requirement equals workload divided by one minus shrinkage fraction), computed per interval where possible (meetings cluster), and its components are measured from actuals, not assumed.
6. Occupancy and service target. For synchronous channels, size to an occupancy ceiling rather than 100 percent utilization, because sustained maximal occupancy degrades quality and drives attrition: the staffing requirement is the larger of the workload-derived requirement and the headcount needed to hold the service target (for example, a stated percentage answered within a stated number of seconds) at the forecast volume, using an accepted queueing method appropriate to the interval.
7. Requirement publication. Publish required productive agents per interval per channel, with the assumptions attached: forecast volume, handle time, shrinkage percent, target, and the multipliers applied. The schedule is built against this sheet and nothing else.
8. Accuracy tracking. Each week, compare forecast to actual per interval; report volume accuracy, interval-level absolute error, and the resulting service impact (intervals where actual service missed target because forecast error, not schedule adherence, drove it).

The two math errors that recur in practice deserve emphasis. First, applying shrinkage as a subtraction from headcount rather than a divisor on productive time understates the requirement (10 staff less 30 percent shrinkage is 7 productive; to get 10 productive you need about 14.3, not 10). Second, averaging daily requirements into a daily number and scheduling to it leaves the intraday peaks unstaffed; the interval is the unit of planning, full stop.

## Controls

- Assumption register: every multiplier, trend factor, and shrinkage component is a named entry with an owner and a review date; unexplained adjustments fail review.
- Outlier governance: exclusions from the base week (incident days, sends) are logged with reason and count, so cleaning cannot quietly improve the forecast.
- Occupancy ceiling: a stated maximum sustained occupancy is enforced in the requirement step and monitored in actuals; breaching it is treated as a staffing failure even when service targets held.
- Version control: published requirement sheets are versioned, and the schedule team works only from the current version; mid-cycle revisions replace, not patch.
- Accuracy accountability: forecast accuracy is reviewed weekly with the forecaster and operations together, and persistent bias (always under- or over-forecasting specific intervals) is corrected in the model, not absorbed by overtime.

## Validation evidence

Evidence the forecast discipline works: week-over-week tables of forecast versus actual volume and workload per interval with percentage error; the log of excluded outlier days with reasons; the shrinkage measurement from actuals showing components; the requirement sheet lineage (volume to workload to gross-up to target check) that a reviewer can recompute; and the service-impact analysis attributing missed-target intervals to forecast error versus adherence versus capability. A back-test on held-out weeks, where the model predicts a past week it was not fitted on, is the strongest single artifact.

## Failure modes and correction

Anchoring on distorted history is the common failure: one viral outage week inflates the base week and the desk overstaffs for a month. Correction: outlier logging, trimmed averages, and review of exclusions.

Flat shrinkage is second: a single 30 percent figure applied to all intervals while meetings cluster on Tuesday mornings, which understates those intervals specifically. Correction: interval-level shrinkage from measured components.

Silent target drift is third: the service target used in sizing quietly loosens during a busy quarter, and the requirement falls without any decision being taken. Correction: the target is part of the assumption register with change approval.

Handle-time drift unmodeled is fourth: new product complexity lengthens interactions, volume forecast stays accurate, and service still degrades. Correction: rolling handle-time measurement feeding the weekly refresh, with a alert on movement beyond tolerance.

## Limitations

Sparse history (new channels, new markets) degrades interval models; the desk should lean on analogous channels with explicit analogy assumptions until local history accumulates. Very small intervals and low volumes make queueing approximations noisy; merging intervals for sizing and splitting for scheduling is an accepted compromise that must be stated. Forecasting cannot absorb unannounced demand shocks (incidents, press); surge processes own those hours. Finally, the requirement is only as good as adherence: a perfect forecast with poor schedule adherence still misses service, which is why the accuracy review separates the two.

## Canonical sources

- NIST SP 800-53 Rev. 5, System and Services Acquisition control family, https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final
- NIST SP 800-137, Information Security Continuous Monitoring (ISCM) for Federal Information Systems and Organizations, https://csrc.nist.gov/pubs/sp/800/137/final
- W3C, Web Content Accessibility Guidelines (WCAG) 2.2, https://www.w3.org/TR/WCAG22/
