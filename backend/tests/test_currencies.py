"""Tests for the currency symbol/formatting helpers."""
import currencies


def test_sym_known_codes():
    assert currencies.sym("EUR") == "€"
    assert currencies.sym("CNY") == "¥"
    assert currencies.sym("USD") == "$"
    assert currencies.sym("GBP") == "£"


def test_sym_none_defaults_to_euro():
    assert currencies.sym(None) == "€"
    assert currencies.sym("") == "€"


def test_sym_unknown_code_passthrough():
    assert currencies.sym("XYZ") == "XYZ"


def test_fmt_thousands_and_symbol():
    assert currencies.fmt(1234.5, "EUR") == "1,234.50 €"
    assert currencies.fmt(1000, "CNY") == "1,000.00 ¥"


def test_fmt_defaults_to_euro():
    assert currencies.fmt(5) == "5.00 €"
