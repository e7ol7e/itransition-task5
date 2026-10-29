# Weyland-Yutani Mining Observatory

A formula-only Google Sheets simulator, a live statistical dashboard, and a
snapshot-consistent PDF reporting service. Task 5, Data Engineering.

- **Generator (anyone with the link can edit):** https://docs.google.com/spreadsheets/d/1uxxmH3IpLPEGzf8j6foVFvSr1yaU-W55qWbIQEBUWQ0/edit
- **Dashboard:** https://task5.evgeniy.win/
- **Source:** https://github.com/e7ol7e/itransition-task5
- **Silent demonstration:** https://task5.evgeniy.win/submission/demo.mp4
- **Sample PDF:** https://task5.evgeniy.win/submission/report.pdf

## Use it

1. Open the generator's **Parameters** tab. Amber cells are inputs.
2. Change mine count/names/capacity, dates, `Normal` or `Uniform`, distribution
   parameters, correlation, weekday factors, trend or events. The active parameter
   labels, mean and standard deviation follow the distribution choice. B19 shows
   configuration validity; invalid settings stop generation with a clear message.
3. The **Data** tab recalculates automatically. Its native chart follows the daily
   network total, including any newly activated mines.
4. Click **Refresh data** in the dashboard. Google export propagation can take a
   few seconds; an unchanged-snapshot message means no newer values were observed.
5. Select Network total or a mine; choose line, bar or stacked area and polynomial
   degree 1–4. Tune any detection parameters and click **Apply analysis**.
6. **Export PDF report** downloads the complete report for the displayed snapshot
   and settings, including all mines, all four tests, charts and an anomaly casebook.
7. Click a chart point, an anomaly's **Inspect** button, or choose any date in the
   **Investigation lab**. See the actual calculation and eligibility for all four
   detectors. Network observations include each mine's contribution to the deviation.
8. Enable **No-event comparison** to overlay the same-seed counterfactual. The lab
   compares detector overlap, unique contributions and coverage of injected events.

All simulation runs in Google Sheets cell formulas. Python prepares the setup
files and reads the public sheet; Google credentials and API keys are not needed.

## Generator model

The simulator supports **1–12 mines** and **3–730 inclusive daily observations**.
Names and relative capacities are independent inputs. Output is tonnes per day.

Normal innovations use the supplied mean and standard deviation. Uniform
innovations use the midpoint and bounds. The correlated baseline is:

```
x[-1] = mean
x[t] = mean + rho * (x[t-1] - mean) + sqrt(1-rho²) * centered_innovation[t]
output[t,m] = round(max(0,x[t,m]) * capacity[m] * weekday_factor[t]
                    * (1+daily_trend)^t * product(event_factors[t,m]), 2)
```

The day index starts at zero. Normal and uniform describe the **innovations**;
smoothing, clipping, calendar factors and events transform the final output.

Six event slots are provided, four enabled by default. Each has a start date,
duration, peak multiplier and probability. A seeded draw decides whether each
mine is affected **once per event**, rather than flickering on and off each day.
The event's Gaussian envelope is centered within its duration, with sigma=duration/6
(at least 0.25 days), and zero effect outside that interval. Overlapping events
multiply; factor 1 disables an event. Probabilities are between 0 and 1.

The SIN/MOD pseudo-random formulas are deterministic for a seed. Change the seed
to obtain another scenario; unrelated spreadsheet edits do not reroll the data.
This is a simulation PRNG, not cryptographic randomness. Stronger rho means more
persistent day-to-day fluctuations; its sqrt(1-rho²) scaling preserves the normal
baseline's stationary variance before clipping and seasonal adjustments.

`generator.py` contains the full cell formulas and creates `generator/*.tsv`,
rich-text HTML and `cells.json`. The live sheet uses ordinary `LET`, `SCAN`, `MAP`,
`SEQUENCE`, `NORM.S.INV`, `INDEX`, and arithmetic formulas. No script runs in it.
To recreate the workbook, add Parameters, Data and Audit tabs, paste the matching HTML
tables at A1, and insert a chart with ranges Data!A1:A731 and Data!N1:N731.
`sheet_setup.py` automates layout of an already populated public sheet.

## Investigation and controlled validation

The formula-only **Audit** tab references the existing Data values and calculates
a separate no-event stream with identical seed, noise, capacity, calendar factors
and trend. Six event records include the formula-selected mine count; per-mine
event masks identify active windows after the probability selection. Neutral,
unselected, weak and out-of-range events remain visible rather than disappearing.

The dashboard reads **one raw CSV export** of Audit!A1:AL738, including metadata
and observations. Visualization-query CSV is deliberately avoided: mixed-type
metadata columns can otherwise lose text through type inference. The reader checks
observed output against the no-event stream multiplied by the exported event
envelopes (rounding tolerance 0.011 t), validates affected mine counts, and rejects
inconsistent exports. It does not generate a replacement production dataset.

A **material event day** has an active event mask, an absolute net effect of at
least **0.01 t**, and a relative net effect of at least **5%** against the rounded
no-event output. Positive output against a zero counterfactual has undefined
percentage and qualifies when its absolute effect is material. Network labels
use the aggregate effect, so opposing or diluted mine effects can fall below the
threshold. Coverage counts flagged material days divided by all material days;
no material days means not applicable. An event is detected when at least one of
its material days is flagged; its full hit/miss counts remain visible.

This is controlled simulator evaluation, **not real-world incident accuracy**.
Flags outside event windows are not automatically false positives. Recovery,
weekday patterns, trends and noise can trigger the raw tests. Overlapping events
share their combined net effect; coincidence does not establish an individual
cause. Disabled detectors retain raw evidence but cannot contribute to the enabled
union. Pairwise overlap is descriptive, not independent confidence.

Inspection uses `/api/inspect/{report_id}?series=...&date=...`, bound to the same
immutable analysis handle as PDF export. Grubbs evidence shows the actual maximum
candidate and critical value on each executed pass, including the stopping pass.
Mine contribution tables reconcile output minus the trailing mean (or full-series
mean during warm-up); printed values may differ slightly because of rounding.
The PDF includes detector overlap, validation, event coverage, Grubbs passes and
up to 20 largest network deviation contribution tables, alongside the complete
existing anomaly casebook.

To add or refresh **only Audit**, run `uv run python install_audit.py`. Existing
Parameters and Data cells are preserved. Set `AUDIT_GID` in `generator.py` to the
new tab's gid if recreating the workbook. `sync_sheet.py` is a full reset utility
that installs default Parameters/Data values; it is not the Audit update workflow.

## Statistical definitions

Statistics are calculated independently for every mine and for a separate daily
total, computed by summing active mines for each date.

| Calculation | Definition |
| --- | --- |
| Mean / median | Arithmetic mean / 50th percentile of daily observations |
| Standard deviation | Sample SD, denominator n−1 |
| Quartiles / IQR | Linear interpolation; IQR = Q3−Q1 |
| IQR test | Strictly below Q1−k×IQR or above Q3+k×IQR |
| Z-score | Absolute deviation from mean / sample SD > threshold |
| Moving-average distance | Absolute percent distance from the previous complete window; tested day excluded |
| Grubbs | Two-sided test, sample SD, Student-t critical value at alpha/(2n) with n−2 degrees of freedom |

The moving-average test has no flag during its initial window. At a zero baseline,
another zero is normal and a positive value is a departure; an undefined percentage
is displayed as n/a. Constant series have zero SD and no z-score/Grubbs flags.

Grubbs defaults to **one pass**. Optional repeated removals are explicitly
exploratory: they are not generalized ESD or a family-wise alpha guarantee.
These are raw-output screens. Trend, weekdays and autocorrelation can produce
flags, and Grubbs assumes approximately normal independent observations.
Flags are not proof of real-world incidents or a promise to identify every
configured generator event.

Enabled methods are combined by union. Each date appears once per series, with
all triggered tests. Total flags are tested independently, not summed mine flags.
Spike/drop direction compares with the trailing baseline, or with the series mean
if a complete window is unavailable. Consecutive same-direction flags are grouped
into episodes only for presentation; every flagged observation remains listed.

Polynomial least-squares fits use a scaled domain for numerical stability. They
are descriptive fits, not forecasts, and may extend outside the physical output
range. With fewer than degree+1 dates, the actual degree is reduced to n−1.

References: [NIST Grubbs test](https://www.itl.nist.gov/div898/handbook/eda/section3/eda35h1.htm),
[NumPy quantiles](https://numpy.org/doc/stable/reference/generated/numpy.quantile.html),
[Google SCAN](https://support.google.com/docs/answer/12569094?hl=en).

## Architecture and data integrity

- `generator.py`: spreadsheet cell definitions and reproducible setup artifacts.
- `analytics.py`: CSV validation, descriptive statistics, four tests and trends.
- `investigation.py`: formula-export reconciliation, controlled validation and
  per-observation evidence; no detector rule overrides.
- `app.py`: FastAPI source reader, analysis API, bounded snapshot/result caches.
- `report.py`: paginated ReportLab PDF with Matplotlib charts and Unicode fonts.
- `static/`: responsive dashboard; native SVG charts, no external chart runtime.

The service fetches only the fixed Google document. Arbitrary URLs are not accepted.
Dates must be unique, ordered and continuous; values finite and nonnegative;
names distinct. Output above 1e12 tonnes/day is rejected as implausible and to
keep numerical operations bounded. Invalid/formula-error rows cause an explicit refresh failure;
the previous displayed snapshot stays visible and is not silently replaced.

A SHA-256-derived content ID identifies observed data, event metadata, masks and
counterfactuals; a separate data-only ID makes output preservation verifiable.
Changing detection settings
reuses its immutable in-memory snapshot. PDF exports use an analysis handle bound
to the data, fetch time and full settings, avoiding a hidden re-fetch during export.
The service retains the most recent 12 snapshots/results; expired exports return
an explicit 409 with refresh instructions. Cache state resets on container restart.
PDF generation is serialized to avoid concurrent Matplotlib work. Above 100 anomaly
episodes, the report keeps every case and observation but omits local episode
charts; full per-series charts are always included.

## Local setup and tests

Use Python 3.15 and install [uv](https://docs.astral.sh/uv/), then:

```powershell
uv sync
uv run python generator.py
uv run python -m unittest discover -v
uv run uvicorn app:app --host 127.0.0.1 --port 8765
```

Open http://127.0.0.1:8765/. The spreadsheet must retain link viewing access.
The tests use independent numerical references, including NIST's Grubbs example,
known cubic fits, constant/zero series, leakage-free moving averages, CSV failure
cases, per-date totals, API validation and PDF evidence/disposition checks.
Investigation tests cover reconciliation failures, weak/overlapping effects,
zero baselines, disabled detectors, pass traces and immutable inspection handles.
With the server running, `uv run python check_browser.py` checks the live lab,
chart/register/date inspection, chart modes, method selection, refresh, PDF export
and mobile layout. Pass a deployed base URL to run it against the public service.

## Deployment

```sh
docker compose up -d --build --wait
```

The dedicated Compose project listens on loopback **5005**; Caddy on loopback
**5004** proxies it, and Cloudflare Tunnel routes task5.evgeniy.win to that listener.
`deploy_vps.py` configures only this application and retains an image for rollback.
Other existing applications are left intact. The container runs as a nonroot user,
with a read-only filesystem, dropped capabilities, bounded memory, a writable
temporary directory and a health check. No credentials are needed.

The silent submission demonstration and sample PDF are in the local `video/` and
`artifacts/` folders, excluded from source control. The demonstration records the
real Google Sheets editor, the deployed dashboard and the generated PDF viewer.
Reviewed copies are served by Caddy from `/var/www/itransition-task5/submission/`
as `demo.mp4` and `report.pdf`; video seeking uses normal HTTP range requests.
The finished video is 1920×1080 at 30 fps, approximately 2 minutes 22 seconds,
with no audio, narration or subtitles.
