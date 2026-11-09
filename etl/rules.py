"""Vectorised cleaning rules (pandas). Each rule takes a Series and returns a Series.

Values that cannot be cleaned become <NA>; the validator turns those into
rejects with a reason, so nothing is silently dropped.
"""
from __future__ import annotations

import re

import pandas as pd

_DATE_FORMATS = ["%Y-%m-%d", "%m/%d/%Y", "%d-%b-%Y", "%Y%m%d"]
_POSTAL_RE = re.compile(r"^([A-Z]\d[A-Z])\s?(\d[A-Z]\d)$")


def strip(s: pd.Series, **_) -> pd.Series:
    return s.astype("string").str.strip()


def title(s: pd.Series, **_) -> pd.Series:
    return strip(s).str.title()


def _split_name(s: pd.Series) -> pd.DataFrame:
    parts = strip(s).str.split(",", n=1, expand=True)
    if parts.shape[1] == 1:
        parts[1] = pd.NA
    return parts.apply(lambda col: col.str.strip().str.title())


def name_first(s: pd.Series, **_) -> pd.Series:
    return _split_name(s)[1]


def name_last(s: pd.Series, **_) -> pd.Series:
    return _split_name(s)[0]


def phone_e164(s: pd.Series, **_) -> pd.Series:
    digits = s.astype("string").str.replace(r"\D", "", regex=True)
    digits = digits.where(~(digits.str.len().eq(11) & digits.str.startswith("1")), digits.str[1:])
    return ("+1" + digits).where(digits.str.len().eq(10), pd.NA)


def email(s: pd.Series, **_) -> pd.Series:
    s = strip(s).str.lower()
    return s.where(s.str.match(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", na=False), pd.NA)


def date(s: pd.Series, **_) -> pd.Series:
    s = strip(s)
    out = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    for fmt in _DATE_FORMATS:
        parsed = pd.to_datetime(s, format=fmt, errors="coerce")
        out = out.fillna(parsed)
    return out.dt.strftime("%Y-%m-%d").astype("string")


def integer(s: pd.Series, **_) -> pd.Series:
    return pd.to_numeric(strip(s), errors="coerce").astype("Int64")


def money_cents(s: pd.Series, **_) -> pd.Series:
    s = strip(s)
    negative = s.str.startswith("(") & s.str.endswith(")")
    cleaned = s.str.replace(r"[\$,()\s]", "", regex=True)
    value = pd.to_numeric(cleaned, errors="coerce")
    cents = (value * 100).round().astype("Int64")
    return cents.where(~negative, -cents)


def postal_ca(s: pd.Series, **_) -> pd.Series:
    s = strip(s).str.upper()
    return s.str.replace(_POSTAL_RE, r"\1 \2", regex=True).where(s.str.match(_POSTAL_RE, na=False), pd.NA)


def status_code(s: pd.Series, *, mapping: dict, **_) -> pd.Series:
    return strip(s).str.upper().map(mapping["status_codes"]).astype("string")


def service_type(s: pd.Series, *, mapping: dict, **_) -> pd.Series:
    return strip(s).str.upper().map(mapping["service_types"]).astype("string")


RULES = {f.__name__: f for f in [strip, title, name_first, name_last, phone_e164, email,
                                  date, integer, money_cents, postal_ca, status_code, service_type]}
