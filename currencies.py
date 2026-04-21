CURRENCIES = {
    "EUR": "€",
    "CNY": "¥",
    "USD": "$",
    "GBP": "£",
}

CURRENCY_LABELS = {
    "EUR": "Euro (€)",
    "CNY": "Chinese Yuan (¥)",
    "USD": "US Dollar ($)",
    "GBP": "British Pound (£)",
}

CURRENCY_LIST = list(CURRENCIES.keys())


def sym(code):
    return CURRENCIES.get(code or "EUR", code or "EUR")


def fmt(amount, code="EUR"):
    return f"{amount:,.2f} {sym(code)}"
