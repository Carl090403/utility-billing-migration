import json
import sqlite3

import pandas as pd
import pytest

from etl import rules
from etl.generate_legacy import build
from etl.pipeline import run

MAPPING = json.load(open("config/mapping.json"))


@pytest.mark.parametrize("raw,expected", [
    ("(613) 555-1234", "+16135551234"), ("613.555.1234", "+16135551234"),
    ("1-613-555-1234", "+16135551234"), ("+1 613 555 1234", "+16135551234"),
    ("N/A", None), ("", None),
])
def test_phone_e164(raw, expected):
    out = rules.phone_e164(pd.Series([raw]))[0]
    assert (out if out is not pd.NA else None) == expected


@pytest.mark.parametrize("raw,expected", [
    ("$1,234.50", 123450), ("1234.5", 123450), ("(12.00)", -1200), ("0.00", 0)])
def test_money_cents(raw, expected):
    assert rules.money_cents(pd.Series([raw]))[0] == expected


@pytest.mark.parametrize("raw", ["2026-03-15", "03/15/2026", "15-Mar-2026", "20260315"])
def test_date_formats(raw):
    assert rules.date(pd.Series([raw]))[0] == "2026-03-15"


def test_name_split_and_postal():
    s = pd.Series(["TREMBLAY, MARIE", "Diallo,Awa "])
    assert list(rules.name_last(s)) == ["Tremblay", "Diallo"]
    assert list(rules.name_first(s)) == ["Marie", "Awa"]
    assert rules.postal_ca(pd.Series(["k2k3c9"]))[0] == "K2K 3C9"


def test_status_mapping():
    assert rules.status_code(pd.Series(["a", "F"]), mapping=MAPPING).tolist() == ["ACTIVE", "FINAL_BILLED"]


@pytest.fixture(scope="module")
def migrated(tmp_path_factory):
    d = tmp_path_factory.mktemp("run")
    truth = build(d / "legacy.db", n_customers=250, seed=7)
    report = run(d / "legacy.db", d / "target.db", d)
    return truth, report, d


def test_financial_reconciliation(migrated):
    truth, report, _ = migrated
    assert report.reconciliation["balance_matches"]
    assert report.reconciliation["target_balance_cents"] == truth["total_balance_cents"]


def test_every_row_accounted_for(migrated):
    _, report, _ = migrated
    assert report.reconciliation["row_accounting_balanced"]


def test_duplicates_merged_and_orphans_rejected(migrated):
    truth, report, d = migrated
    assert report.duplicates_merged == truth["duplicate_customer_rows"]
    assert report.loaded_rows["customer"] == truth["customers"]
    rejects = pd.read_csv(d / "rejects.csv")
    assert (rejects["reject_reason"].str.startswith("orphan")).sum() >= truth["orphan_readings"]


def test_target_integrity(migrated):
    _, _, d = migrated
    con = sqlite3.connect(d / "target.db")
    assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    assert con.execute("SELECT COUNT(*) FROM customer WHERE phone_e164 NOT LIKE '+1%'").fetchone()[0] == 0
