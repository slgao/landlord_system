#! /usr/bin/env python
# coding=utf-8
# ================================================================
#   Copyright (C) 2026 * Ltd. All rights reserved.
#
#   Editor      : EMACS
#   File name   : logic.py
#   Author      : slgao
#   Created date: Sun Mar 08 2026 18:21:07
#   Description :
#
# ================================================================
from db import fetch


def strom_calc(cost_flat, tenants, days, limit_per_month=50):

    cost_per_tenant = cost_flat / tenants
    limit_day = (limit_per_month * 12) / 365 / tenants
    limit_period = limit_day * days
    nachzahlung = cost_per_tenant - limit_period

    return cost_per_tenant, limit_period, nachzahlung


def betriebskosten_calc(cost_flat, tenants, months, bk_start, bk_end, limit_per_month=206):

    num_months = (bk_end.year - bk_start.year) * 12 + (bk_end.month - bk_start.month + 1)
    if num_months == 0:
        num_months = 1
    cost_per_tenant = cost_flat / tenants
    period_cost = cost_per_tenant / num_months * months
    limit_month = limit_per_month / tenants
    limit_period = limit_month * months
    nachzahlung = period_cost - limit_period

    return cost_per_tenant, period_cost, limit_period, nachzahlung


def dashboard_stats():

    properties = fetch("SELECT COUNT(*) FROM properties")[0][0]
    apartments = fetch("SELECT COUNT(*) FROM apartments")[0][0]
    tenants = fetch("SELECT COUNT(*) FROM tenants")[0][0]
    contracts = fetch("SELECT COUNT(*) FROM contracts")[0][0]

    rent = fetch("SELECT SUM(rent) FROM contracts")[0][0]

    if rent is None:
        rent = 0

    return {
        "properties": properties,
        "apartments": apartments,
        "tenants": tenants,
        "contracts": contracts,
        "rent": rent,
    }


def tenant_ledger(tenant_id):

    payments = fetch(
        """
    SELECT amount,payment_date
    FROM payments
    JOIN contracts ON payments.contract_id = contracts.id
    WHERE contracts.tenant_id = ?
    """,
        (tenant_id,),
    )

    return payments
