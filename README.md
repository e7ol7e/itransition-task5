# Weyland-Yutani Mining Observatory

A formula-only Google Sheets simulator, a live statistical dashboard, and a
snapshot-consistent PDF reporting service. Task 5, Data Engineering.

- **Generator (anyone with the link can edit):** https://docs.google.com/spreadsheets/d/1uxxmH3IpLPEGzf8j6foVFvSr1yaU-W55qWbIQEBUWQ0/edit
- **Dashboard:** https://task5.evgeniy.win/
- **Source:** https://github.com/e7ol7e/itransition-task5

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

There is no Apps Script, server-generated production dataset, or canned-data
fallback. Python prepares formula setup files, then reads the actual Google Sheet.
The dashboard works without Google credentials, API keys or a paid Google API.

## Generator model

The simulator supports **1–12 mines** and **3–730 inclusive daily observations**.
Names and relative capacities are independent inputs. Output is tonnes per day.

Normal innovations use the supplied mean and standard deviation. Uniform
innovations use the midpoint and bounds. The correlated baseline is:

```
x[t] = mean + rho * (x[t-1] - mean) + sqrt(1-rho²) * centered_innovation[t]
x[0] = mean
output[t,m] = round(max(0,x[t,m]) * capacity[m] * weekday_factor[t]
                    * (1+daily_trend)^t * product(event_factors[t,m]), 2)
```

Normal and uniform describe the **innovations**, not a claim that final output
retains that distribution after smoothing, calendar effects and events.

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
To recreate the workbook, add Parameters and Data tabs, paste the matching HTML
tables at A1, and insert a chart with ranges Data!A1:A731 and Data!N1:N731.
`sheet_setup.py` automates layout of an already populated public sheet.

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
- `app.py`: FastAPI source reader, analysis API, bounded snapshot/result caches.
- `report.py`: paginated ReportLab PDF with Matplotlib charts and Unicode fonts.
- `static/`: responsive dashboard; native SVG charts, no external chart runtime.

The service fetches only the fixed Google document. Arbitrary URLs are not accepted.
Dates must be unique, ordered and continuous; values finite and nonnegative;
names distinct. Output above 1e12 tonnes/day is rejected as implausible and to
keep numerical operations bounded. Invalid/formula-error rows cause an explicit refresh failure;
the previous displayed snapshot stays visible and is not silently replaced.

A SHA-256-derived content ID identifies each dataset. Changing detection settings
reuses its immutable in-memory snapshot. PDF exports use an analysis handle bound
to the data, fetch time and full settings, avoiding a hidden re-fetch during export.
The service retains the most recent 12 snapshots/results; expired exports return
an explicit 409 with refresh instructions. Cache state resets on container restart.
PDF generation is serialized to avoid concurrent Matplotlib work. Above 100 anomaly
episodes, the report keeps every case and observation but omits local episode
charts; full per-series charts are always included.

## Local setup and tests

Install [uv](https://docs.astral.sh/uv/), then:

```powershell
uv sync
uv run python generator.py
uv run python -m unittest test_analytics test_api -v
uv run uvicorn app:app --host 127.0.0.1 --port 8765
```

Open http://127.0.0.1:8765/. The spreadsheet must retain link viewing access.
The tests use independent numerical references, including NIST's Grubbs example,
known cubic fits, constant/zero series, leakage-free moving averages, CSV failure
cases, per-date totals, API validation and PDF evidence/disposition checks.

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
