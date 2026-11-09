"""Extract -> Profile -> Transform -> Validate -> Load pipeline.

Run:  python -m etl.pipeline --legacy output/legacy_cis.db --target output/target.db
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from etl.rules import RULES

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {
    "customer": ["account_number", "last_name", "status"],
    "premise": ["premise_id", "account_number"],
    "meter": ["meter_number", "premise_id", "service_type"],
    "reading": ["meter_number", "read_on", "read_value"],
    "balance": ["account_number", "balance_cents"],
}
TARGET_DDL = """
CREATE TABLE customer (account_number TEXT PRIMARY KEY, first_name TEXT, last_name TEXT NOT NULL,
    phone_e164 TEXT, email TEXT, status TEXT NOT NULL, opened_on TEXT);
CREATE TABLE premise (premise_id TEXT PRIMARY KEY, account_number TEXT NOT NULL REFERENCES customer,
    address_line1 TEXT, city TEXT, postal_code TEXT);
CREATE TABLE meter (meter_number TEXT PRIMARY KEY, premise_id TEXT NOT NULL REFERENCES premise,
    service_type TEXT NOT NULL, installed_on TEXT);
CREATE TABLE reading (meter_number TEXT NOT NULL REFERENCES meter, read_on TEXT NOT NULL,
    read_value INTEGER NOT NULL, PRIMARY KEY (meter_number, read_on));
CREATE TABLE balance (account_number TEXT PRIMARY KEY REFERENCES customer, balance_cents INTEGER NOT NULL);
"""


@dataclass
class RunReport:
    source_rows: dict = field(default_factory=dict)
    loaded_rows: dict = field(default_factory=dict)
    rejects: dict = field(default_factory=dict)
    duplicates_merged: int = 0
    reconciliation: dict = field(default_factory=dict)
    seconds: float = 0.0


# ----------------------------------------------------------------- profiling
def profile(con: sqlite3.Connection) -> str:
    """Markdown profile of every legacy table: nulls, distinct, top patterns."""
    lines = ["# Legacy schema profile", ""]
    tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    for t in tables:
        df = pd.read_sql(f"SELECT * FROM {t}", con)
        lines += [f"## {t} — {len(df)} rows", "", "| column | null/blank % | distinct | top patterns |",
                  "|---|---|---|---|"]
        for c in df.columns:
            s = df[c].astype("string")
            blank = (s.isna() | s.str.strip().eq("")).mean() * 100
            pattern = (s.fillna("").str.replace(r"[A-Za-z]", "a", regex=True)
                       .str.replace(r"\d", "9", regex=True))
            top = ", ".join(f"`{p}`" for p in pattern.value_counts().head(3).index)
            lines.append(f"| {c} | {blank:.1f} | {s.nunique()} | {top} |")
        lines.append("")
    return "\n".join(lines)


# ----------------------------------------------------------------- transform
def transform_entity(raw: pd.DataFrame, spec: dict, mapping: dict) -> pd.DataFrame:
    out = pd.DataFrame(index=raw.index)
    for target_col, col_spec in spec["columns"].items():
        rule = RULES[col_spec["rule"]]
        out[target_col] = rule(raw[col_spec["from"]], mapping=mapping)
    return out


def split_rejects(df: pd.DataFrame, entity: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    missing = df[REQUIRED[entity]].isna()
    bad = missing.any(axis=1)
    rejects = df[bad].copy()
    rejects["reject_reason"] = pd.Series(
        ["missing/invalid: " + ", ".join(row.index[row]) for _, row in missing[bad].iterrows()],
        index=rejects.index, dtype="string")
    return df[~bad], rejects


def dedupe_customers(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Keep the most complete record per account (survivorship rule)."""
    completeness = df.notna().sum(axis=1)
    df = df.assign(_score=completeness).sort_values("_score", ascending=False)
    deduped = df.drop_duplicates("account_number", keep="first").drop(columns="_score")
    return deduped.sort_index(), len(df) - len(deduped)


def enforce_fk(child: pd.DataFrame, col: str, parent_keys: pd.Series) -> tuple[pd.DataFrame, pd.DataFrame]:
    ok = child[col].isin(parent_keys)
    orphans = child[~ok].copy()
    orphans["reject_reason"] = f"orphan: {col} not found in parent"
    return child[ok], orphans


# ----------------------------------------------------------------- run
def run(legacy_db: Path, target_db: Path, out_dir: Path, mapping_path: Path | None = None) -> RunReport:
    t0 = time.perf_counter()
    mapping = json.loads((mapping_path or ROOT / "config" / "mapping.json").read_text())
    report = RunReport()
    out_dir.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(legacy_db) as src:
        (out_dir / "profile_legacy.md").write_text(profile(src))
        raw = {e: pd.read_sql(f"SELECT * FROM {s['source']}", src) for e, s in mapping["entities"].items()}

    clean, rejects = {}, []
    for entity, spec in mapping["entities"].items():
        report.source_rows[entity] = len(raw[entity])
        df = transform_entity(raw[entity], spec, mapping)
        df, rej = split_rejects(df, entity)
        rejects.append(rej.assign(entity=entity))
        clean[entity] = df

    clean["customer"], report.duplicates_merged = dedupe_customers(clean["customer"])
    clean["reading"] = clean["reading"].drop_duplicates(["meter_number", "read_on"])

    for child, col, parent, pcol in [("premise", "account_number", "customer", "account_number"),
                                     ("meter", "premise_id", "premise", "premise_id"),
                                     ("reading", "meter_number", "meter", "meter_number"),
                                     ("balance", "account_number", "customer", "account_number")]:
        clean[child], orphans = enforce_fk(clean[child], col, clean[parent][pcol])
        rejects.append(orphans.assign(entity=child))

    all_rejects = pd.concat(rejects, ignore_index=True)
    all_rejects.to_csv(out_dir / "rejects.csv", index=False)
    report.rejects = all_rejects.groupby("entity").size().to_dict()

    if target_db.exists():
        target_db.unlink()
    with sqlite3.connect(target_db) as tgt:
        tgt.executescript(TARGET_DDL)
        for entity in ["customer", "premise", "meter", "reading", "balance"]:
            clean[entity].to_sql(entity, tgt, if_exists="append", index=False)
            report.loaded_rows[entity] = len(clean[entity])
        report.reconciliation = reconcile(raw, tgt, report)

    report.seconds = round(time.perf_counter() - t0, 3)
    (out_dir / "run_report.json").write_text(json.dumps(report.__dict__, indent=2, default=int))
    return report


def reconcile(raw: dict, tgt: sqlite3.Connection, report: RunReport) -> dict:
    """Financial + count reconciliation: every source row is either loaded, merged or rejected."""
    src_balance = int(RULES["money_cents"](raw["balance"]["BAL_AMT"]).sum())
    tgt_balance = tgt.execute("SELECT COALESCE(SUM(balance_cents),0) FROM balance").fetchone()[0]
    counts_ok = all(
        report.source_rows[e] == report.loaded_rows[e] + report.rejects.get(e, 0)
        + (report.duplicates_merged if e == "customer" else 0)
        + (report.source_rows[e] - len(raw[e].drop_duplicates()) if e == "reading" else 0)
        for e in report.source_rows
    )
    fk_violations = tgt.execute("PRAGMA foreign_key_check").fetchall()
    return {
        "source_balance_cents": src_balance,
        "target_balance_cents": tgt_balance,
        "balance_matches": src_balance == tgt_balance,
        "row_accounting_balanced": counts_ok,
        "foreign_key_violations": len(fk_violations),
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--legacy", type=Path, default=ROOT / "output" / "legacy_cis.db")
    p.add_argument("--target", type=Path, default=ROOT / "output" / "target.db")
    p.add_argument("--out", type=Path, default=ROOT / "output")
    a = p.parse_args()
    r = run(a.legacy, a.target, a.out)
    print(json.dumps(r.__dict__, indent=2, default=int))


if __name__ == "__main__":
    main()
