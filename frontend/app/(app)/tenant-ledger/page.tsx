"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Tenant, Contract, Payment } from "@/lib/types";
import { PageHeader } from "@/components/page-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";

export default function TenantLedgerPage() {
  const [tenantId, setTenantId] = useState<string>("");

  const { data: tenants = [] } = useQuery<Tenant[]>({
    queryKey: ["tenants"],
    queryFn: () => api.get("/api/tenants/").then((r) => r.data),
  });
  const { data: contracts = [] } = useQuery<Contract[]>({
    queryKey: ["tenant-contracts", tenantId],
    queryFn: () => api.get(`/api/contracts/tenant/${tenantId}`).then((r) => r.data),
    enabled: !!tenantId,
  });
  const { data: payments = [] } = useQuery<Payment[]>({
    queryKey: ["tenant-payments", tenantId],
    queryFn: () => api.get(`/api/payments/?tenant_id=${tenantId}`).then((r) => r.data),
    enabled: !!tenantId,
  });

  const totalPaid = payments.reduce((s, p) => s + p.amount, 0);
  const totalRent = contracts.reduce((s, c) => s + c.rent, 0);
  const CURRENCY_SYMBOLS: Record<string, string> = { EUR: "€", CNY: "¥", USD: "$", GBP: "£" };
  const perCurrency = payments.reduce((acc, p) => {
    const curr = p.currency || "EUR";
    acc[curr] = (acc[curr] || 0) + p.amount;
    return acc;
  }, {} as Record<string, number>);

  return (
    <div className="max-w-4xl">
      <PageHeader title="Tenant Ledger">
        <Select value={tenantId} onValueChange={setTenantId}>
          <SelectTrigger className="w-52 h-8 text-sm">
            <SelectValue placeholder="Select tenant" />
          </SelectTrigger>
          <SelectContent>
            {tenants.map((t) => (
              <SelectItem key={t.id} value={String(t.id)}>{t.name}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </PageHeader>

      {!tenantId ? (
        <p className="text-muted-foreground text-sm">Select a tenant to view their ledger.</p>
      ) : (
        <div className="space-y-4">
          {/* Summary */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {Object.entries(perCurrency).map(([curr, total]) => (
              <Card key={curr}>
                <CardContent className="p-4">
                  <p className="text-xs text-muted-foreground uppercase tracking-wide">Total Paid ({curr})</p>
                  <p className="text-2xl font-semibold mt-1">{CURRENCY_SYMBOLS[curr] || curr} {total.toFixed(2)}</p>
                </CardContent>
              </Card>
            ))}
            <Card>
              <CardContent className="p-4">
                <p className="text-xs text-muted-foreground uppercase tracking-wide">Payments</p>
                <p className="text-2xl font-semibold mt-1">{payments.length}</p>
              </CardContent>
            </Card>
          </div>

          {/* Contracts */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">Contracts</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Apartment</TableHead>
                    <TableHead>Rent</TableHead>
                    <TableHead>Start</TableHead>
                    <TableHead>End</TableHead>
                    <TableHead>Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {contracts.map((c) => (
                    <TableRow key={c.id}>
                      <TableCell>{c.apartment_name}<br /><span className="text-xs text-muted-foreground">{c.property_name}</span></TableCell>
                      <TableCell>{c.rent.toFixed(2)} {c.currency}</TableCell>
                      <TableCell className="text-muted-foreground">{c.start_date}</TableCell>
                      <TableCell className="text-muted-foreground">{c.end_date || "—"}</TableCell>
                      <TableCell>
                        <Badge variant={c.terminated ? "secondary" : "default"} className={!c.terminated ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/20" : ""}>
                          {c.terminated ? "Ended" : "Active"}
                        </Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          {/* Payment history */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">Payment History</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Date</TableHead>
                    <TableHead>Apartment</TableHead>
                    <TableHead>Amount</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {payments.length === 0 ? (
                    <TableRow><TableCell colSpan={3} className="text-center text-muted-foreground py-6">No payments on record.</TableCell></TableRow>
                  ) : (
                    payments.map((p) => (
                      <TableRow key={p.id}>
                        <TableCell className="text-muted-foreground">{p.payment_date}</TableCell>
                        <TableCell>{p.apartment_name}</TableCell>
                        <TableCell className="font-mono">
                          {p.amount.toFixed(2)} EUR
                          {p.orig_currency && p.orig_amount != null && (
                            <span className="block text-xs text-muted-foreground">
                              (paid {CURRENCY_SYMBOLS[p.orig_currency] || p.orig_currency}{p.orig_amount.toFixed(2)})
                            </span>
                          )}
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
