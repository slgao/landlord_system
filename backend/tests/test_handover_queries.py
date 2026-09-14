"""Reading a protocol must not cost a round trip per reading.

The database is ~38 ms away, so query *count* is the cost model: a WG flat
reads six meters, and two lookups per reading meant fourteen round trips.
"""
import pytest

from api.routers import handover


def _install(monkeypatch, readings):
    """readings: [(id, meter_type, meter_id)] — returns the SQL that was run."""
    seen = []

    def fake_fetch(sql, params=()):
        q = " ".join(sql.split())
        seen.append(q)
        if "FROM handover_protocols WHERE id=" in q:
            return [(1, "2026-01-01")]                       # _own_protocol
        if "FROM meter_readings m" in q:
            return [(rid, mt, mid, "2026-01-01", 100.0, None) for rid, mt, mid in readings]
        if "serial_number, description FROM" in q:
            return [(mid, f"SER-{mid}", None) for _, _, mid in readings]
        if "FROM meter_reading_protocols mrp" in q:
            return [(rid, 99, "move_in", "Tenant") for rid, _, _ in readings]
        raise AssertionError(f"unexpected query: {q}")

    monkeypatch.setattr(handover, "fetch", fake_fetch)
    return seen


def test_query_count_does_not_grow_with_the_number_of_readings(monkeypatch):
    one = _install(monkeypatch, [(1, "strom", 10)])
    handover.list_protocol_readings(1, owner=1)
    six = _install(monkeypatch, [(i, "strom", 10 + i) for i in range(1, 7)])
    handover.list_protocol_readings(1, owner=1)
    # Same meter type throughout: protocol + readings + one meter lookup + one
    # attribution lookup, however many readings there are.
    assert len(one) == len(six) == 4


def test_one_lookup_per_meter_type_present(monkeypatch):
    seen = _install(monkeypatch, [(1, "strom", 10), (2, "gas", 20), (3, "strom", 11)])
    handover.list_protocol_readings(1, owner=1)
    meter_queries = [q for q in seen if "serial_number, description FROM" in q]
    assert len(meter_queries) == 2                 # strom and gas, not three readings
    assert sum("FROM meter_reading_protocols mrp" in q for q in seen) == 1


def test_the_rows_are_still_right(monkeypatch):
    _install(monkeypatch, [(7, "strom", 10)])
    rows = handover.list_protocol_readings(1, owner=1)
    assert len(rows) == 1
    assert rows[0].id == 7 and rows[0].serial_number == "SER-10"
    assert rows[0].also_at == ["Einzug · Tenant"]


def test_the_protocol_itself_is_excluded_from_also_at(monkeypatch):
    """A reading's own protocol is not 'also taken at' itself."""
    def fake_fetch(sql, params=()):
        q = " ".join(sql.split())
        if "FROM handover_protocols WHERE id=" in q:
            return [(1, "2026-01-01")]
        if "FROM meter_readings m" in q:
            return [(1, "strom", 10, "2026-01-01", 5.0, None)]
        if "serial_number, description FROM" in q:
            return [(10, "SER-10", None)]
        if "FROM meter_reading_protocols mrp" in q:
            # the same reading, seen by this protocol (55) and another (99)
            return [(1, 55, "move_out", "Alice"), (1, 99, "move_in", "Bob")]
        raise AssertionError(q)
    monkeypatch.setattr(handover, "fetch", fake_fetch)
    rows = handover.list_protocol_readings(55, owner=1)
    assert rows[0].also_at == ["Einzug · Bob"]


def test_no_readings_costs_no_lookups(monkeypatch):
    seen = _install(monkeypatch, [])
    assert handover.list_protocol_readings(1, owner=1) == []
    assert len(seen) == 2                          # protocol + the empty readings query
