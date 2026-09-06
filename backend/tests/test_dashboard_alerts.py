"""Dashboard stats/alerts: a contract signed before its start date is not
running yet, and must be reported as upcoming rather than active."""
from datetime import date, timedelta

import pytest

from api.routers import dashboard


def _iso(days: int) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


def _rows(monkeypatch, rows):
    monkeypatch.setattr(dashboard, "fetch", lambda sql, params=(): rows)


def test_upcoming_contract_is_flagged_not_expiring(monkeypatch):
    _rows(monkeypatch, [("Tenant A", "Flat 1", "House", _iso(30), _iso(400))])
    (alert,) = dashboard.alerts(owner=1)
    assert alert["level"] == "upcoming"
    assert alert["days_remaining"] == 30
    assert alert["start_date"] == _iso(30)


def test_upcoming_contract_beyond_the_window_is_quiet(monkeypatch):
    _rows(monkeypatch, [("Tenant A", "Flat 1", "House", _iso(120), None)])
    assert dashboard.alerts(owner=1) == []


def test_not_yet_started_contract_never_counts_as_expired(monkeypatch):
    # Nonsense dates (ends before it starts) must not produce an "expired" row.
    _rows(monkeypatch, [("Tenant A", "Flat 1", "House", _iso(10), _iso(-5))])
    (alert,) = dashboard.alerts(owner=1)
    assert alert["level"] == "upcoming"


def test_running_contracts_still_warn_and_expire(monkeypatch):
    _rows(monkeypatch, [
        ("Ends soon", "Flat 1", "House", _iso(-400), _iso(20)),
        ("Lapsed",    "Flat 2", "House", _iso(-800), _iso(-3)),
        ("Open end",  "Flat 3", "House", _iso(-100), "None"),
        ("Far off",   "Flat 4", "House", _iso(-100), _iso(400)),
    ])
    levels = [(a["tenant_name"], a["level"]) for a in dashboard.alerts(owner=1)]
    # Lapsed first (most urgent), then the one running out; open-ended and
    # far-off contracts are not alerts at all.
    assert levels == [("Lapsed", "expired"), ("Ends soon", "warning")]


def test_alerts_are_ordered_expired_then_warning_then_upcoming(monkeypatch):
    _rows(monkeypatch, [
        ("Starts later", "Flat 1", "House", _iso(60), None),
        ("Ends soon",    "Flat 2", "House", _iso(-400), _iso(10)),
        ("Lapsed",       "Flat 3", "House", _iso(-800), _iso(-1)),
        ("Starts sooner", "Flat 4", "House", _iso(5), None),
    ])
    assert [a["tenant_name"] for a in dashboard.alerts(owner=1)] == [
        "Lapsed", "Ends soon", "Starts sooner", "Starts later"]


def test_unparsable_dates_are_skipped(monkeypatch):
    _rows(monkeypatch, [("Tenant A", "Flat 1", "House", "not-a-date", "also-bad")])
    assert dashboard.alerts(owner=1) == []


def test_stats_split_running_from_upcoming(monkeypatch):
    today = date.today().isoformat()
    seen = []

    def fake_fetch(sql, params=()):
        seen.append((" ".join(sql.split()), params))
        return [[7]]

    monkeypatch.setattr(dashboard, "fetch", fake_fetch)
    out = dashboard.stats(owner=1)
    assert out["contracts"] == 7 and out["upcoming"] == 7
    contract_queries = [(sql, p) for sql, p in seen if "FROM contracts" in sql]
    assert [p[1] for _, p in contract_queries] == [today, today]
    assert "start_date<=?" in contract_queries[0][0]
    assert "start_date>?" in contract_queries[1][0]
