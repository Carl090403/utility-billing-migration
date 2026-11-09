# Utility Billing Data Migration (Legacy CIS → Cloud CIS)

A metadata-driven **ETL pipeline in Python + pandas + SQL** that migrates a messy legacy
utility billing database (customers, premises, meters, readings, A/R balances) into a clean,
constrained target schema — with **schema profiling, data-quality rules, a rejects file and
financial reconciliation**.

Built to mirror the day-to-day work of a utility data conversion team: legacy schemas you did
not design, dirty data, and a go-live where **every dollar and every row must be accounted for**.

## Why this project
| Real-world conversion problem | How it is handled |
|---|---|
| Unknown legacy schema | `profile()` produces `output/profile_legacy.md`: null %, distinct counts, value *patterns* per column |
| Every client's legacy system is different | Mappings live in `config/mapping.json` (metadata-driven) — onboard a new client by editing config, not code |
| Dirty values (6 phone formats, 4 date formats, `"(12.00)"` credits) | Vectorised pandas rules in `etl/rules.py` → E.164 phones, ISO dates, integer cents |
| Duplicate customers | Survivorship rule: keep the most complete record per account |
| Orphan rows | Foreign-key enforcement before load; orphans go to `rejects.csv` with a reason |
| "Did we lose money?" | Reconciliation: source A/R total == target A/R total, to the cent |
| "Did we lose rows?" | Row accounting: `source = loaded + merged + rejected` for every entity |

## Run it
```bash
pip install -r requirements.txt
python -m etl.generate_legacy      # builds output/legacy_cis.db (synthetic, messy, seeded)
python -m etl.pipeline             # profile -> transform -> validate -> load -> reconcile
python -m pytest -q                # 20 tests
```

Sample run (400 customers):
```
loaded: customer 400 | premise 400 | meter 604 | reading 3624 | balance 400
duplicates merged: 19   rejects: 12 orphan readings
balance_matches: true (96,847.06 $)   row_accounting_balanced: true   FK violations: 0
```

## Structure
```
etl/generate_legacy.py   synthetic legacy CIS with realistic defects + true control totals
etl/rules.py             cleaning rules (phone, date, money, postal code, status codes...)
etl/pipeline.py          profiling, transform, rejects, dedupe, FK checks, load, reconciliation
config/mapping.json      source→target column mapping + legacy code tables
tests/                   unit tests per rule + end-to-end reconciliation tests
.github/workflows/ci.yml CI: generate, migrate, test on every push
```

## Design choices
* **Nothing is silently dropped.** A value that cannot be cleaned becomes `NA`; if the field is
  required, the row goes to `rejects.csv` with a human-readable reason a client can act on.
* **Money in integer cents** — no floating-point drift in financial totals.
* **Idempotent runs** — the target is rebuilt from scratch, so a conversion can be re-run
  after each round of client feedback (mock conversions 1, 2, 3… before go-live).

## Next steps
Incremental (delta) loads · conversion audit dashboard · parallel extraction per table ·
loading into PostgreSQL instead of SQLite.
