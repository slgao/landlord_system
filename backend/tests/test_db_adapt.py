"""Tests for db._adapt — the SQLite-style → psycopg2 query translator.

Getting this wrong silently corrupts every query, so the escaping rules are
worth pinning down: literal % must double (psycopg2 treats % as a format
marker), ? becomes %s, and date('now') maps to a TEXT-comparable current date.
"""
import db


def test_question_marks_become_percent_s():
    assert db._adapt("SELECT * FROM t WHERE id=?") == "SELECT * FROM t WHERE id=%s"


def test_multiple_placeholders():
    assert db._adapt("INSERT INTO t VALUES (?,?,?)") == "INSERT INTO t VALUES (%s,%s,%s)"


def test_literal_percent_is_escaped():
    # LIKE wildcards must survive as %% so psycopg2 doesn't misread them.
    assert db._adapt("WHERE name LIKE '%foo%'") == "WHERE name LIKE '%%foo%%'"


def test_date_now_maps_to_current_date():
    assert db._adapt("WHERE d <= date('now')") == "WHERE d <= CURRENT_DATE::TEXT"


def test_combined_translation():
    src = "SELECT * FROM t WHERE d <= date('now') AND n LIKE '%x%' AND id=?"
    expected = "SELECT * FROM t WHERE d <= CURRENT_DATE::TEXT AND n LIKE '%%x%%' AND id=%s"
    assert db._adapt(src) == expected


def test_plain_query_unchanged():
    assert db._adapt("SELECT 1") == "SELECT 1"
