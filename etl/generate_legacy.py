"""Generate a realistic, intentionally *messy* legacy utility billing database.

The goal is to reproduce the problems a data conversion engineer meets when
migrating a utility from a legacy CIS (Customer Information System) to a modern
cloud platform:

* names stored as "LAST, FIRST" in a single column, inconsistent casing
* phone numbers in 6+ different formats
* dates stored as text in several formats
* money stored as text ("$1,234.50", "1234.5", "(12.00)" for credits)
* duplicate customer records created by front-desk staff
* orphan rows (readings that point to meters that no longer exist)
* cryptic legacy status codes
"""
from __future__ import annotations

import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

FIRST = ["Marie", "Jean", "Aminata", "Liam", "Olivia", "Noah", "Fatou", "Ethan",
         "Chloé", "Lucas", "Awa", "Emma", "Mohamed", "Sophie", "Kofi", "Léa"]
LAST = ["Tremblay", "Gagnon", "Diallo", "Smith", "Roy", "Côté", "Brown", "Kone",
        "Martin", "Wilson", "Traoré", "Lee", "Bouchard", "Mensah", "Nguyen"]
STREETS = ["Bank St", "Rideau St", "Elgin St", "Carling Ave", "March Rd",
           "Terry Fox Dr", "Hazeldean Rd", "Montreal Rd"]
SERVICE = {"W": "water", "E": "electric", "G": "gas"}
LEGACY_STATUS = ["A", "A", "A", "A", "I", "F", "P"]  # Active/Inactive/Final/Pending


def _phone(rng: random.Random) -> str:
    a, b, c = rng.choice(["613", "343", "819"]), rng.randint(200, 999), rng.randint(1000, 9999)
    fmt = rng.choice([
        f"({a}) {b}-{c}", f"{a}-{b}-{c}", f"{a}.{b}.{c}", f"{a}{b}{c}",
        f"+1 {a} {b} {c}", f"1-{a}-{b}-{c}", "", "N/A",
    ])
    return fmt


def _date_text(rng: random.Random, d: date) -> str:
    return rng.choice([
        d.strftime("%Y-%m-%d"), d.strftime("%m/%d/%Y"), d.strftime("%d-%b-%Y"),
        d.strftime("%Y%m%d"),
    ])


def _money_text(rng: random.Random, cents: int) -> str:
    value = cents / 100
    if value < 0:
        return f"({abs(value):,.2f})"
    return rng.choice([f"${value:,.2f}", f"{value:.2f}", f"{value:.1f}" if cents % 10 == 0 else f"{value:.2f}"])


def build(db_path: Path, n_customers: int = 400, seed: int = 42) -> dict:
    """Create the legacy database and return the *true* control totals.

    The control totals are what an auditor would compute directly in the
    legacy system; the ETL must reconcile against them.
    """
    rng = random.Random(seed)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.executescript(
        """
        CREATE TABLE CUSTMAST (           -- legacy customer master
            CUST_NO      TEXT,            -- not enforced unique!
            CUST_NAME    TEXT,            -- 'LAST, FIRST'
            PHONE        TEXT,
            EMAIL        TEXT,
            STAT_CD      TEXT,
            OPEN_DT      TEXT
        );
        CREATE TABLE PREMISE (
            PREM_ID      TEXT,
            CUST_NO      TEXT,
            ADDR1        TEXT,
            CITY         TEXT,
            POSTAL       TEXT
        );
        CREATE TABLE METER (
            METER_NO     TEXT,
            PREM_ID      TEXT,
            SVC_TYPE     TEXT,           -- W/E/G
            INSTALL_DT   TEXT
        );
        CREATE TABLE READING (
            METER_NO     TEXT,
            READ_DT      TEXT,
            READ_VAL     TEXT            -- numeric stored as text
        );
        CREATE TABLE ARBAL (              -- accounts receivable balance
            CUST_NO      TEXT,
            BAL_AMT      TEXT            -- '$1,234.50' or '(12.00)' for credit
        );
        """
    )

    true_balance_cents = 0
    duplicates = 0
    orphan_readings = 0
    for i in range(1, n_customers + 1):
        cust_no = f"{i:07d}"
        first, last = rng.choice(FIRST), rng.choice(LAST)
        name = rng.choice([f"{last.upper()}, {first.upper()}", f"{last}, {first}", f"{last},{first} "])
        email = rng.choice([f"{first}.{last}@example.com".lower(), "", f"{first}{i}@mail.ca".lower()])
        opened = date(2005, 1, 1) + timedelta(days=rng.randint(0, 7000))
        status = rng.choice(LEGACY_STATUS)
        cur.execute("INSERT INTO CUSTMAST VALUES (?,?,?,?,?,?)",
                    (cust_no, name, _phone(rng), email, status, _date_text(rng, opened)))
        # ~4% duplicate customer rows (same CUST_NO, slightly different data)
        if rng.random() < 0.04:
            duplicates += 1
            cur.execute("INSERT INTO CUSTMAST VALUES (?,?,?,?,?,?)",
                        (f" {cust_no}", name.lower(), _phone(rng), email, status, _date_text(rng, opened)))

        prem_id = f"P{i:06d}"
        postal = f"K{rng.randint(1,2)}{rng.choice('ABCEGHJKLMNPRSTVXY')} {rng.randint(0,9)}{rng.choice('ABCEGHJKLMNPRSTVXY')}{rng.randint(0,9)}"
        cur.execute("INSERT INTO PREMISE VALUES (?,?,?,?,?)",
                    (prem_id, cust_no, f"{rng.randint(1, 2999)} {rng.choice(STREETS)}",
                     rng.choice(["Ottawa", "OTTAWA", "Kanata", "Nepean"]),
                     rng.choice([postal, postal.replace(" ", ""), postal.lower()])))

        for svc in rng.sample(list(SERVICE), k=rng.randint(1, 2)):
            meter = f"{svc}{i:06d}"
            cur.execute("INSERT INTO METER VALUES (?,?,?,?)",
                        (meter, prem_id, rng.choice([svc, svc.lower()]),
                         _date_text(rng, opened + timedelta(days=rng.randint(0, 60)))))
            value = rng.randint(100, 5000)
            for m in range(6):
                value += rng.randint(5, 400)
                cur.execute("INSERT INTO READING VALUES (?,?,?)",
                            (meter, _date_text(rng, date(2026, 1 + m, 15)), str(value)))

        cents = rng.randint(-5000, 60000) if status != "I" else 0
        true_balance_cents += cents
        cur.execute("INSERT INTO ARBAL VALUES (?,?)", (cust_no, _money_text(rng, cents)))

    # Orphan readings: meters removed from METER table but readings kept
    for k in range(12):
        orphan_readings += 1
        cur.execute("INSERT INTO READING VALUES (?,?,?)", (f"X{k:06d}", "2026-03-15", "123"))

    con.commit()
    con.close()
    return {
        "customers": n_customers,
        "duplicate_customer_rows": duplicates,
        "orphan_readings": orphan_readings,
        "total_balance_cents": true_balance_cents,
    }


if __name__ == "__main__":
    import json
    totals = build(Path("output/legacy_cis.db"))
    Path("output/legacy_control_totals.json").write_text(json.dumps(totals, indent=2))
    print(json.dumps(totals, indent=2))
