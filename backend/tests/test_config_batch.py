"""Reading the settings page must not cost a round trip per setting.

The database is ~25 ms away, so query *count* is the cost model: five
`get_config()` calls were five round trips — 125 ms of waiting for 171 bytes.
`get_configs()` asks for the lot at once, and must stay a drop-in for the dict
comprehension it replaced: every key present, missing ones defaulted.
"""
import db


def _install(monkeypatch, stored):
    """Answers the batched read from `stored`, and records the SQL it ran."""
    seen = []

    def fake_fetch(sql, params=()):
        seen.append((" ".join(sql.split()), params))
        keys = params[1:]            # params[0] is the owner
        return [(k, v) for k, v in stored.items() if k in keys]

    monkeypatch.setattr(db, "fetch", fake_fetch)
    monkeypatch.setattr(db, "current_owner", lambda: 1)
    return seen


def test_many_keys_cost_one_query(monkeypatch):
    seen = _install(monkeypatch, {"a": "1", "b": "2", "c": "3"})
    assert db.get_configs(["a", "b", "c"]) == {"a": "1", "b": "2", "c": "3"}
    assert len(seen) == 1


def test_a_missing_key_comes_back_as_the_default(monkeypatch):
    _install(monkeypatch, {"a": "1"})
    assert db.get_configs(["a", "b"]) == {"a": "1", "b": None}
    assert db.get_configs(["a", "b"], default="") == {"a": "1", "b": ""}


def test_the_result_is_scoped_to_the_current_owner(monkeypatch):
    seen = _install(monkeypatch, {"a": "1"})
    db.get_configs(["a"])
    sql, params = seen[0]
    assert "owner_id=?" in sql
    assert params[0] == 1


def test_no_keys_asks_nothing(monkeypatch):
    seen = _install(monkeypatch, {"a": "1"})
    assert db.get_configs([]) == {}
    assert seen == []


def test_keys_are_passed_as_parameters_not_interpolated(monkeypatch):
    """A config key is data. It reaches the database as a bound parameter."""
    seen = _install(monkeypatch, {})
    db.get_configs(["smtp_host", "smtp_port"])
    sql, params = seen[0]
    assert "smtp_host" not in sql
    assert params == (1, "smtp_host", "smtp_port")
