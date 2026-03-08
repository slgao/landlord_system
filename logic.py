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

def strom_calc(cost_flat, tenants, days):

    cost_per_tenant = cost_flat / tenants

    limit_day = (50*12)/365/tenants

    limit_period = limit_day * days

    nachzahlung = cost_per_tenant - limit_period

    return cost_per_tenant, limit_period, nachzahlung


def betriebskosten_calc(cost_flat, tenants, months):

    cost_per_tenant = cost_flat / tenants

    period_cost = cost_per_tenant/12 * months

    limit_month = 206/tenants

    limit_period = limit_month * months

    nachzahlung = period_cost - limit_period

    return cost_per_tenant, period_cost, limit_period, nachzahlung
