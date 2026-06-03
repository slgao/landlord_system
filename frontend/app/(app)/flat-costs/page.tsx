"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { FlatCost, Apartment } from "@/lib/types";
import { PageHeader } from "@/components/page-header";
import { GroupCard } from "@/components/group-card";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";
import { ConfirmButton } from "@/components/confirm-button";
import { Pencil, Trash2, Plus } from "lucide-react";

const FREQ = ["monthly", "quarterly", "annually", "one-time"];
const EMPTY = { apartment_id: 0, cost_type: "", amount: 0, frequency: "monthly", valid_from: "", valid_to: "" };

// Normalise any frequency to a monthly-equivalent amount for the summary.
function monthlyEquivalent(fc: FlatCost): number {
  switch (fc.frequency) {
    case "monthly": return fc.amount;
    case "quarterly": return fc.amount / 3;
    case "annually": return fc.amount / 12;
    default: return 0; // one-time not counted in the recurring monthly figure
  }
}

export default function FlatCostsPage() {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<FlatCost | null>(null);
  const [form, setForm] = useState<typeof EMPTY>(EMPTY);
  const [filterProp, setFilterProp] = useState("all");

  const { data: flatCosts = [], isLoading } = useQuery<FlatCost[]>({
    queryKey: ["flat-costs"],
    queryFn: () => api.get("/api/flat-costs/").then((r) => r.data),
  });
  const { data: apartments = [] } = useQuery<Apartment[]>({
    queryKey: ["apartments"],
    queryFn: () => api.get("/api/apartments/").then((r) => r.data),
  });

  const save = useMutation({
    mutationFn: (data: typeof EMPTY) => {
      const body = { ...data, valid_from: data.valid_from || null, valid_to: data.valid_to || null };
      return editing ? api.put(`/api/flat-costs/${editing.id}`, body) : api.post("/api/flat-costs/", body);
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["flat-costs"] }); toast.success(editing ? "Updated" : "Created"); setOpen(false); },
    onError: () => toast.error("Failed to save"),
  });

  const remove = useMutation({
    mutationFn: (id: number) => api.delete(`/api/flat-costs/${id}`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["flat-costs"] }); toast.success("Deleted"); },
  });

  function openCreate(apartmentId?: number) {
    setEditing(null);
    setForm({ ...EMPTY, apartment_id: apartmentId ?? 0 });
    setOpen(true);
  }
  function openEdit(f: FlatCost) {
    setEditing(f);
    setForm({ apartment_id: f.apartment_id, cost_type: f.cost_type, amount: f.amount, frequency: f.frequency, valid_from: f.valid_from || "", valid_to: f.valid_to || "" });
    setOpen(true);
  }

  // Group apartments (that have costs OR exist) by property, then by apartment.
  const properties = Array.from(new Set(apartments.map((a) => a.property_name || "—"))).sort();
  const visibleProps = filterProp === "all" ? properties : properties.filter((p) => p === filterProp);

  const costsByApartment = (aptId: number) => flatCosts.filter((fc) => fc.apartment_id === aptId);
  const grandMonthly = flatCosts.reduce((s, fc) => s + monthlyEquivalent(fc), 0);

  return (
    <div className="max-w-4xl space-y-4">
      <PageHeader title="Flat Costs" description="Recurring costs grouped per apartment"
        action={{ label: "New Cost", onClick: () => openCreate() }}>
        <Select value={filterProp} onValueChange={setFilterProp}>
          <SelectTrigger className="w-48 h-8 text-sm"><SelectValue placeholder="All properties" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All properties</SelectItem>
            {properties.map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}
          </SelectContent>
        </Select>
      </PageHeader>

      {/* Grand total */}
      <Card className="p-4 flex items-center justify-between">
        <span className="text-sm text-muted-foreground">Total recurring cost (monthly equivalent)</span>
        <span className="text-xl font-semibold">€ {grandMonthly.toFixed(2)}</span>
      </Card>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : apartments.length === 0 ? (
        <p className="text-sm text-muted-foreground">No apartments yet — add one first.</p>
      ) : (
        visibleProps.map((propName) => {
          const apts = apartments.filter((a) => (a.property_name || "—") === propName);
          return (
            <div key={propName} className="space-y-2">
              <h2 className="text-xs font-medium uppercase tracking-widest text-muted-foreground px-1 pt-2">{propName}</h2>
              {apts.map((apt) => {
                const costs = costsByApartment(apt.id);
                const monthly = costs.reduce((s, fc) => s + monthlyEquivalent(fc), 0);
                return (
                  <GroupCard
                    key={apt.id}
                    title={apt.name}
                    subtitle={apt.flat ? `Unit ${apt.flat}` : undefined}
                    defaultOpen={costs.length > 0}
                    summary={
                      <>
                        <Badge variant="secondary">{costs.length} cost{costs.length !== 1 ? "s" : ""}</Badge>
                        {monthly > 0 && <span className="text-sm font-medium">€ {monthly.toFixed(2)}/mo</span>}
                      </>
                    }
                  >
                    {costs.length === 0 ? (
                      <div className="px-4 py-3 flex items-center justify-between">
                        <span className="text-sm text-muted-foreground">No costs for this apartment.</span>
                        <Button variant="outline" size="sm" onClick={() => openCreate(apt.id)}>
                          <Plus className="size-4 mr-1" /> Add cost
                        </Button>
                      </div>
                    ) : (
                      <>
                        <Table>
                          <TableHeader>
                            <TableRow>
                              <TableHead>Type</TableHead>
                              <TableHead className="text-right">Amount</TableHead>
                              <TableHead>Frequency</TableHead>
                              <TableHead>Valid</TableHead>
                              <TableHead className="w-20" />
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {costs.map((fc) => (
                              <TableRow key={fc.id}>
                                <TableCell className="font-medium">{fc.cost_type}</TableCell>
                                <TableCell className="text-right font-mono">{fc.amount.toFixed(2)} €</TableCell>
                                <TableCell className="text-muted-foreground capitalize">{fc.frequency}</TableCell>
                                <TableCell className="text-muted-foreground text-xs">
                                  {fc.valid_from || "—"}{fc.valid_to ? ` → ${fc.valid_to}` : ""}
                                </TableCell>
                                <TableCell>
                                  <div className="flex gap-1 justify-end">
                                    <Button variant="ghost" size="icon" onClick={() => openEdit(fc)}><Pencil className="size-4" /></Button>
                                    <ConfirmButton onConfirm={() => remove.mutate(fc.id)} title="Delete cost?" message={`Delete "${fc.cost_type}" (${fc.amount.toFixed(2)} €)?`}>
                                      <Button variant="ghost" size="icon" className="text-destructive hover:text-destructive"><Trash2 className="size-4" /></Button>
                                    </ConfirmButton>
                                  </div>
                                </TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                        <div className="px-4 py-2 border-t border-border">
                          <Button variant="ghost" size="sm" onClick={() => openCreate(apt.id)}>
                            <Plus className="size-4 mr-1" /> Add cost to {apt.name}
                          </Button>
                        </div>
                      </>
                    )}
                  </GroupCard>
                );
              })}
            </div>
          );
        })
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>{editing ? "Edit Cost" : "New Cost"}</DialogTitle></DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1.5">
              <Label>Apartment</Label>
              <Select value={String(form.apartment_id || "")} onValueChange={(v) => setForm((f) => ({ ...f, apartment_id: Number(v) }))}>
                <SelectTrigger><SelectValue placeholder="Select" /></SelectTrigger>
                <SelectContent>
                  {apartments.map((a) => <SelectItem key={a.id} value={String(a.id)}>{a.property_name} — {a.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label>Cost Type</Label>
                <Input value={form.cost_type} onChange={(e) => setForm((f) => ({ ...f, cost_type: e.target.value }))} placeholder="e.g. Hausgeld" />
              </div>
              <div className="space-y-1.5">
                <Label>Amount (€)</Label>
                <Input type="number" step="0.01" value={form.amount} onChange={(e) => setForm((f) => ({ ...f, amount: Number(e.target.value) }))} />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label>Frequency</Label>
              <Select value={form.frequency} onValueChange={(v) => setForm((f) => ({ ...f, frequency: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>{FREQ.map((fr) => <SelectItem key={fr} value={fr} className="capitalize">{fr}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label>Valid From</Label>
                <Input type="date" value={form.valid_from} onChange={(e) => setForm((f) => ({ ...f, valid_from: e.target.value }))} />
              </div>
              <div className="space-y-1.5">
                <Label>Valid To</Label>
                <Input type="date" value={form.valid_to} onChange={(e) => setForm((f) => ({ ...f, valid_to: e.target.value }))} />
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button onClick={() => save.mutate(form)} disabled={!form.apartment_id || !form.cost_type || save.isPending}>
              {save.isPending ? "Saving…" : "Save"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
