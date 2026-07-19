"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { TaxProfile, TaxExpense, NkSplit } from "@/lib/types";
import { PageHeader } from "@/components/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { ConfirmButton } from "@/components/confirm-button";
import { toast } from "sonner";
import { Plus, Save, Trash2, FileDown } from "lucide-react";

const eur = (v: number) =>
  v.toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " €";

// ── Profiles (purchase / AfA) ────────────────────────────────────────────────

function ProfileRow({ p }: { p: TaxProfile }) {
  const qc = useQueryClient();
  const toggleRelevance = useMutation({
    mutationFn: () => api.put(`/api/tax/properties/${p.property_id}/relevance`, {
      tax_relevant: !p.tax_relevant,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tax-profiles"] });
      qc.invalidateQueries({ queryKey: ["tax-report"] });
      toast.success(p.tax_relevant
        ? `${p.property_name} excluded from tax report`
        : `${p.property_name} included in tax report`);
    },
    onError: () => toast.error("Failed to update"),
  });
  const [f, setF] = useState({
    purchase_date: p.purchase_date ?? "",
    purchase_price: p.purchase_price != null ? String(p.purchase_price) : "",
    building_share_pct: p.building_share_pct != null ? String(p.building_share_pct) : "",
    afa_rate_pct: p.afa_rate_pct != null ? String(p.afa_rate_pct) : "2.0",
    notes: p.notes ?? "",
  });

  const save = useMutation({
    mutationFn: () => api.put(`/api/tax/profiles/${p.property_id}`, {
      purchase_date: f.purchase_date || null,
      purchase_price: f.purchase_price ? parseFloat(f.purchase_price) : null,
      building_share_pct: f.building_share_pct ? parseFloat(f.building_share_pct) : null,
      afa_rate_pct: f.afa_rate_pct ? parseFloat(f.afa_rate_pct) : null,
      notes: f.notes || null,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tax-profiles"] });
      toast.success(`${p.property_name} saved`);
    },
    onError: () => toast.error("Failed to save"),
  });

  const afaPreview =
    f.purchase_price && f.building_share_pct && f.afa_rate_pct
      ? (parseFloat(f.purchase_price) * parseFloat(f.building_share_pct) * parseFloat(f.afa_rate_pct)) / 10000
      : null;

  return (
    <TableRow className={p.tax_relevant ? "" : "opacity-45"}>
      <TableCell>
        <Button
          size="sm"
          variant={p.tax_relevant ? "default" : "outline"}
          className="h-7 px-2 text-xs"
          disabled={toggleRelevance.isPending}
          onClick={() => toggleRelevance.mutate()}
          title={p.tax_relevant
            ? "Included in the tax report — click to exclude (e.g. not your property)"
            : "Excluded from the tax report — click to include"}
        >
          {p.tax_relevant ? "Declared" : "Excluded"}
        </Button>
      </TableCell>
      <TableCell className="font-medium">{p.property_name}</TableCell>
      <TableCell><Input type="date" className="h-8 w-36" value={f.purchase_date}
        onChange={(e) => setF({ ...f, purchase_date: e.target.value })} /></TableCell>
      <TableCell><Input type="number" step="1000" placeholder="Price €" className="h-8 w-28 font-mono"
        value={f.purchase_price} onChange={(e) => setF({ ...f, purchase_price: e.target.value })} /></TableCell>
      <TableCell><Input type="number" step="1" placeholder="%" className="h-8 w-16 font-mono"
        value={f.building_share_pct} onChange={(e) => setF({ ...f, building_share_pct: e.target.value })} /></TableCell>
      <TableCell><Input type="number" step="0.5" className="h-8 w-16 font-mono"
        value={f.afa_rate_pct} onChange={(e) => setF({ ...f, afa_rate_pct: e.target.value })} /></TableCell>
      <TableCell className="text-right font-mono text-muted-foreground">
        {afaPreview != null ? `${eur(afaPreview)}/yr` : "—"}
      </TableCell>
      <TableCell>
        <Button size="sm" variant="outline" disabled={save.isPending} onClick={() => save.mutate()}>
          <Save className="size-4" />
        </Button>
      </TableCell>
    </TableRow>
  );
}

// ── Mortgages ────────────────────────────────────────────────────────────────

const EMPTY_MORTGAGE = {
  property_id: "", label: "", principal: "", interest_rate_pct: "",
  tilgung_rate_pct: "", start_date: "",
};

function MortgageSection({ profiles }: { profiles: TaxProfile[] }) {
  const qc = useQueryClient();
  const [f, setF] = useState(EMPTY_MORTGAGE);
  const mortgages = profiles.flatMap((p) =>
    p.mortgages.map((m) => ({ ...m, property_name: p.property_name })));

  const invalidate = () => qc.invalidateQueries({ queryKey: ["tax-profiles"] });

  const add = useMutation({
    mutationFn: () => api.post("/api/tax/mortgages", {
      property_id: parseInt(f.property_id),
      label: f.label || null,
      principal: parseFloat(f.principal),
      interest_rate_pct: parseFloat(f.interest_rate_pct),
      tilgung_rate_pct: parseFloat(f.tilgung_rate_pct),
      start_date: f.start_date,
    }),
    onSuccess: () => { invalidate(); setF(EMPTY_MORTGAGE); toast.success("Mortgage added"); },
    onError: () => toast.error("Failed to add"),
  });

  const del = useMutation({
    mutationFn: (id: number) => api.delete(`/api/tax/mortgages/${id}`),
    onSuccess: () => { invalidate(); toast.success("Mortgage removed"); },
  });

  const valid = f.property_id && f.principal && f.interest_rate_pct && f.tilgung_rate_pct && f.start_date;

  return (
    <Card>
      <CardContent className="p-4 space-y-3">
        <p className="font-medium">Mortgages (Annuitätendarlehen)</p>
        <p className="text-xs text-muted-foreground">
          Schuldzinsen are computed month-by-month from these terms. A manual
          &quot;Schuldzinsen&quot; expense for a year overrides the computation
          (use the bank&apos;s Jahreskontoauszug — authoritative with Sondertilgungen).
        </p>
        {mortgages.length > 0 && (
          <Table>
            <TableHeader><TableRow>
              <TableHead>Property</TableHead><TableHead>Label</TableHead>
              <TableHead className="text-right">Principal</TableHead>
              <TableHead className="text-right">Sollzins %</TableHead>
              <TableHead className="text-right">Tilgung %</TableHead>
              <TableHead>Start</TableHead><TableHead />
            </TableRow></TableHeader>
            <TableBody>
              {mortgages.map((m) => (
                <TableRow key={m.id}>
                  <TableCell>{m.property_name}</TableCell>
                  <TableCell className="text-muted-foreground">{m.label || "—"}</TableCell>
                  <TableCell className="text-right font-mono">{eur(m.principal)}</TableCell>
                  <TableCell className="text-right font-mono">{m.interest_rate_pct}</TableCell>
                  <TableCell className="text-right font-mono">{m.tilgung_rate_pct}</TableCell>
                  <TableCell className="text-muted-foreground">{m.start_date}</TableCell>
                  <TableCell>
                    <ConfirmButton onConfirm={() => del.mutate(m.id)}
                      message={`Delete mortgage ${m.label || m.id} (${m.property_name})? Computed Schuldzinsen for it disappear from all years.`}>
                      <Button size="sm" variant="ghost" className="text-muted-foreground"><Trash2 className="size-4" /></Button>
                    </ConfirmButton>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
        <div className="flex flex-wrap items-end gap-2">
          <div className="space-y-1"><Label className="text-xs">Property</Label>
            <Select value={f.property_id} onValueChange={(v) => setF({ ...f, property_id: v })}>
              <SelectTrigger className="h-8 w-40"><SelectValue placeholder="Select…" /></SelectTrigger>
              <SelectContent>{profiles.map((p) => (
                <SelectItem key={p.property_id} value={String(p.property_id)}>{p.property_name}</SelectItem>
              ))}</SelectContent>
            </Select></div>
          <div className="space-y-1"><Label className="text-xs">Bank / label</Label>
            <Input className="h-8 w-32" value={f.label} onChange={(e) => setF({ ...f, label: e.target.value })} /></div>
          <div className="space-y-1"><Label className="text-xs">Loan €</Label>
            <Input type="number" className="h-8 w-28 font-mono" value={f.principal} onChange={(e) => setF({ ...f, principal: e.target.value })} /></div>
          <div className="space-y-1"><Label className="text-xs">Sollzins %</Label>
            <Input type="number" step="0.01" className="h-8 w-20 font-mono" value={f.interest_rate_pct} onChange={(e) => setF({ ...f, interest_rate_pct: e.target.value })} /></div>
          <div className="space-y-1"><Label className="text-xs">Tilgung %</Label>
            <Input type="number" step="0.01" className="h-8 w-20 font-mono" value={f.tilgung_rate_pct} onChange={(e) => setF({ ...f, tilgung_rate_pct: e.target.value })} /></div>
          <div className="space-y-1"><Label className="text-xs">First payment</Label>
            <Input type="date" className="h-8 w-36" value={f.start_date} onChange={(e) => setF({ ...f, start_date: e.target.value })} /></div>
          <Button size="sm" disabled={!valid || add.isPending} onClick={() => add.mutate()}>
            <Plus className="size-4 mr-1" /> Add
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

// ── Kaltmiete / NK split per contract ────────────────────────────────────────

function NkRow({ c }: { c: NkSplit }) {
  const qc = useQueryClient();
  const [nk, setNk] = useState(
    c.nebenkosten_vorauszahlung != null ? String(c.nebenkosten_vorauszahlung) : "");

  const save = useMutation({
    mutationFn: () => api.put(`/api/tax/nk-splits/${c.contract_id}`, {
      nebenkosten_vorauszahlung: nk === "" ? null : parseFloat(nk),
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tax-nk-splits"] });
      qc.invalidateQueries({ queryKey: ["tax-report"] });
      toast.success(`${c.tenant_name} saved`);
    },
    onError: () => toast.error("Failed to save"),
  });

  const kalt = nk !== "" ? c.rent - parseFloat(nk || "0") : null;
  return (
    <TableRow className={c.end_date ? "opacity-50" : ""}>
      <TableCell className="text-muted-foreground">{c.property_name}</TableCell>
      <TableCell className="font-medium">{c.tenant_name}</TableCell>
      <TableCell className="text-muted-foreground">{c.apartment_name}{c.end_date ? ` (ended ${c.end_date})` : ""}</TableCell>
      <TableCell className="text-right font-mono">{eur(c.rent)}</TableCell>
      <TableCell>
        <Input type="number" step="1" placeholder="NK €/mo" className="h-8 w-24 font-mono"
          value={nk} onChange={(e) => setNk(e.target.value)} />
      </TableCell>
      <TableCell className="text-right font-mono text-muted-foreground">
        {kalt != null && !isNaN(kalt) ? eur(kalt) : "—"}
      </TableCell>
      <TableCell>
        <Button size="sm" variant="outline" disabled={save.isPending} onClick={() => save.mutate()}>
          <Save className="size-4" />
        </Button>
      </TableCell>
    </TableRow>
  );
}

function NkSection() {
  const { data: splits = [] } = useQuery<NkSplit[]>({
    queryKey: ["tax-nk-splits"],
    queryFn: () => api.get("/api/tax/nk-splits").then((r) => r.data),
  });
  const missing = splits.filter((s) => !s.end_date && s.nebenkosten_vorauszahlung == null).length;

  return (
    <Card>
      <CardContent className="p-4 space-y-3">
        <p className="font-medium">Kaltmiete / Umlagen split (per contract)</p>
        <p className="text-xs text-muted-foreground">
          Anlage V reports Kaltmiete and Umlagen (NK-Vorauszahlungen) on separate lines.
          Enter the monthly NK portion of each contract&apos;s rent — Kaltmiete is derived.
          {missing > 0 && <span className="text-amber-500"> {missing} active contract{missing !== 1 ? "s" : ""} still missing the NK portion.</span>}
        </p>
        <Table>
          <TableHeader><TableRow>
            <TableHead>Property</TableHead><TableHead>Tenant</TableHead>
            <TableHead>Apartment</TableHead>
            <TableHead className="text-right">Rent (warm)</TableHead>
            <TableHead>NK / month</TableHead>
            <TableHead className="text-right">Kaltmiete</TableHead><TableHead />
          </TableRow></TableHeader>
          <TableBody>
            {splits.map((c) => <NkRow key={c.contract_id} c={c} />)}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

// ── One-off expenses ─────────────────────────────────────────────────────────

const EMPTY_EXPENSE = {
  property_id: "", expense_date: "", amount: "", category: "Erhaltungsaufwand",
  vendor: "", note: "", distribute_years: "1",
};

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function ExpenseSection({ profiles }: { profiles: TaxProfile[] }) {
  const qc = useQueryClient();
  const [f, setF] = useState(EMPTY_EXPENSE);
  const [invYear, setInvYear] = useState(String(new Date().getFullYear() - 1));

  async function downloadInventory() {
    const token = localStorage.getItem("token");
    const res = await fetch(`${API}/api/tax/expenses/inventory/pdf?year=${invYear}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) {
      toast.error(res.status === 404 ? `No expenses recorded for ${invYear}` : "PDF failed");
      return;
    }
    const blob = await res.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `Belegliste_${invYear}.pdf`;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  const { data: categories = [] } = useQuery<string[]>({
    queryKey: ["tax-expense-categories"],
    queryFn: () => api.get("/api/tax/expense-categories").then((r) => r.data),
  });
  const { data: expenses = [] } = useQuery<TaxExpense[]>({
    queryKey: ["tax-expenses"],
    queryFn: () => api.get("/api/tax/expenses").then((r) => r.data),
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["tax-expenses"] });
  };

  const add = useMutation({
    mutationFn: () => api.post("/api/tax/expenses", {
      property_id: parseInt(f.property_id),
      expense_date: f.expense_date,
      amount: parseFloat(f.amount),
      category: f.category,
      vendor: f.vendor || null,
      note: f.note || null,
      distribute_years: parseInt(f.distribute_years) || 1,
    }),
    onSuccess: () => { invalidate(); setF(EMPTY_EXPENSE); toast.success("Expense added"); },
    onError: () => toast.error("Failed to add"),
  });

  const del = useMutation({
    mutationFn: (id: number) => api.delete(`/api/tax/expenses/${id}`),
    onSuccess: () => { invalidate(); toast.success("Expense removed"); },
  });

  const valid = f.property_id && f.expense_date && f.amount && f.category;

  return (
    <Card>
      <CardContent className="p-4 space-y-3">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <p className="font-medium">One-off expenses</p>
          <div className="flex items-center gap-1.5">
            <Input type="number" className="h-8 w-20 font-mono" value={invYear}
              onChange={(e) => setInvYear(e.target.value)} />
            <Button size="sm" variant="outline" onClick={downloadInventory}>
              <FileDown className="size-4 mr-1" /> Belegliste PDF
            </Button>
          </div>
        </div>
        <p className="text-xs text-muted-foreground">
          Repairs, insurance, yearly mortgage interest (category Schuldzinsen), etc.
          Large repairs can be spread over 2–5 years (§82b EStDV) via &quot;Spread years&quot;.
          The Belegliste PDF lists every bill of a year per property with subtotals and a
          grand total across all flats.
        </p>
        {expenses.length > 0 && (
          <Table>
            <TableHeader><TableRow>
              <TableHead>Date</TableHead><TableHead>Property</TableHead>
              <TableHead>Category</TableHead><TableHead>Vendor</TableHead>
              <TableHead>Beleg</TableHead>
              <TableHead className="text-right">Amount</TableHead>
              <TableHead className="text-right">Spread</TableHead><TableHead />
            </TableRow></TableHeader>
            <TableBody>
              {expenses.map((e) => (
                <TableRow key={e.id}>
                  <TableCell className="text-muted-foreground">{e.expense_date}</TableCell>
                  <TableCell>{e.property_name}</TableCell>
                  <TableCell>{e.category}</TableCell>
                  <TableCell className="text-muted-foreground">{e.vendor || "—"}</TableCell>
                  <TableCell className="text-muted-foreground text-xs" title={e.source_file ?? undefined}>
                    {e.source_file ? e.source_file.split("/").pop() : "—"}
                  </TableCell>
                  <TableCell className="text-right font-mono">{eur(e.amount)}</TableCell>
                  <TableCell className="text-right font-mono">{e.distribute_years > 1 ? `${e.distribute_years}y` : "—"}</TableCell>
                  <TableCell>
                    <ConfirmButton onConfirm={() => del.mutate(e.id)}
                      message={`Delete ${e.category} expense of ${eur(e.amount)} (${e.property_name})?`}>
                      <Button size="sm" variant="ghost" className="text-muted-foreground"><Trash2 className="size-4" /></Button>
                    </ConfirmButton>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
        <div className="flex flex-wrap items-end gap-2">
          <div className="space-y-1"><Label className="text-xs">Property</Label>
            <Select value={f.property_id} onValueChange={(v) => setF({ ...f, property_id: v })}>
              <SelectTrigger className="h-8 w-40"><SelectValue placeholder="Select…" /></SelectTrigger>
              <SelectContent>{profiles.map((p) => (
                <SelectItem key={p.property_id} value={String(p.property_id)}>{p.property_name}</SelectItem>
              ))}</SelectContent>
            </Select></div>
          <div className="space-y-1"><Label className="text-xs">Date paid</Label>
            <Input type="date" className="h-8 w-36" value={f.expense_date} onChange={(e) => setF({ ...f, expense_date: e.target.value })} /></div>
          <div className="space-y-1"><Label className="text-xs">Amount €</Label>
            <Input type="number" step="0.01" className="h-8 w-28 font-mono" value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} /></div>
          <div className="space-y-1"><Label className="text-xs">Category</Label>
            <Select value={f.category} onValueChange={(v) => setF({ ...f, category: v })}>
              <SelectTrigger className="h-8 w-44"><SelectValue /></SelectTrigger>
              <SelectContent>{categories.map((c) => (
                <SelectItem key={c} value={c}>{c}</SelectItem>
              ))}</SelectContent>
            </Select></div>
          <div className="space-y-1"><Label className="text-xs">Vendor</Label>
            <Input className="h-8 w-32" value={f.vendor} onChange={(e) => setF({ ...f, vendor: e.target.value })} /></div>
          <div className="space-y-1"><Label className="text-xs">Spread years</Label>
            <Input type="number" min="1" max="5" className="h-8 w-16 font-mono" value={f.distribute_years} onChange={(e) => setF({ ...f, distribute_years: e.target.value })} /></div>
          <Button size="sm" disabled={!valid || add.isPending} onClick={() => add.mutate()}>
            <Plus className="size-4 mr-1" /> Add
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function TaxSetupPage() {
  const { data: profiles = [], isLoading } = useQuery<TaxProfile[]>({
    queryKey: ["tax-profiles"],
    queryFn: () => api.get("/api/tax/profiles").then((r) => r.data),
  });

  return (
    <div className="max-w-5xl space-y-4">
      <PageHeader
        title="Tax Setup"
        description="One-time purchase/AfA data, mortgages, and one-off expenses feeding the Tax Report"
      />
      {isLoading ? (
        <p className="text-muted-foreground text-sm">Loading…</p>
      ) : (
        <>
          <Card>
            <CardContent className="p-4 space-y-3">
              <p className="font-medium">Purchase data &amp; AfA per property</p>
              <p className="text-xs text-muted-foreground">
                AfA base = purchase price × building share (land is not depreciable).
                Rate: 2&nbsp;% (built 1925–2022) · 2.5&nbsp;% (pre-1925) · 3&nbsp;% (2023+).
                Inherited/gifted properties continue the predecessor&apos;s AfA — note it in the report.
                Use <span className="font-medium">Tax scope</span> to exclude properties you
                don&apos;t own (managed for others) from the tax report entirely.
              </p>
              <Table>
                <TableHeader><TableRow>
                  <TableHead>Tax scope</TableHead>
                  <TableHead>Property</TableHead><TableHead>Purchase date</TableHead>
                  <TableHead>Price</TableHead><TableHead>Building %</TableHead>
                  <TableHead>AfA %</TableHead>
                  <TableHead className="text-right">AfA / year</TableHead><TableHead />
                </TableRow></TableHeader>
                <TableBody>
                  {profiles.map((p) => <ProfileRow key={p.property_id} p={p} />)}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
          <NkSection />
          <MortgageSection profiles={profiles} />
          <ExpenseSection profiles={profiles} />
        </>
      )}
    </div>
  );
}
