#! /usr/bin/env python
# coding=utf-8
# ================================================================
#   Copyright (C) 2026 * Ltd. All rights reserved.
#
#   Editor      : EMACS
#   File name   : app.py
#   Author      : slgao
#   Created date: Sun Mar 08 2026 16:11:33
#   Description : Entry point — sidebar routing only.
#                 All page logic lives in pages/.
# ================================================================

import streamlit as st
from db import init_db

init_db()

st.set_page_config(page_title="Landlord Management System", layout="wide")

from page_modules import (
    dashboard,
    properties,
    apartments,
    tenants,
    tenant_ledger,
    contracts,
    rent_tracking,
    flat_costs,
    balance_sheet,
    nebenkostenabrechnung,
    mahnung,
    payment_reminders,
)

PAGES = {
    "Dashboard":             dashboard.show,
    "Properties":            properties.show,
    "Apartments":            apartments.show,
    "Tenants":               tenants.show,
    "Tenant Ledger":         tenant_ledger.show,
    "Contracts":             contracts.show,
    "Rent Tracking":         rent_tracking.show,
    "Flat Costs":            flat_costs.show,
    "Balance Sheet":         balance_sheet.show,
    "Payment Reminders":     payment_reminders.show,
    "Nebenkostenabrechnung": nebenkostenabrechnung.show,
    "Mahnung Generator":     mahnung.show,
}

menu = st.sidebar.selectbox("Menu", list(PAGES.keys()))
PAGES[menu]()
