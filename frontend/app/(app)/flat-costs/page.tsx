"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { FlatCost, Apartment } from "@/lib/types";
import { PageHeader } from "@/components/page-header";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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
import { Pencil, Trash2 } from "lucide-react";

const FREQ = ["monthly", "quarterly", "annually", "one-time"];
const EMPTY = { apartment_id: 0, cost_type: "", amount: 0, frequency: "monthly", valid_from: "", valid_to: "" };

export default function FlatCostsPage() {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<FlatCost | null>(null);
  const [form, setForm] = useState<typeof EMPTY>(EMPTY);

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
      return editing
        ? api.put(`/api/flat-costs/${editing.id}`, body)
        : api.post("/api/flat-costs/", body);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["flat-costs"] });
      toast.success(editing ? "Updated" : "Created");
      setOpen(false);
    },
    onError: () => toast.error("Failed to save"),
  });

  const remove = useMutation({
    mutationFn: (id: number) => api.delete(`/api/flat-costs/${id}`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["flat-costs"] }); toast.success("Deleted"); },
  });

  function openCreate() { setEditing(null); setForm(EMPTY); setOpen(true); }
  function openEdit(f: FlatCost) {
    setEditing(f);
    setForm({ apartment_id: f.apartment_id, cost_type: f.cost_type, amount: f.amount, frequency: f.frequency, valid_from: f.valid_from || "", valid_to: f.valid_to || "" });
    setOpen(true);
  }

  return (
    <div className="max-w-4xl">
      <PageHeader title="Flat Costs" description="Recurring costs per apartment" action={{ label: "New Cost", onClick: openCreate }} />

      <Card>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Apartment</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Amount</TableHead>
              <TableHead>Frequency</TableHead>
              <TableHead>Valid From</TableHead>
              <TableHead>Valid To</TableHead>
              <TableHead className="w-20" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow><TableCell colSpan={7} className="text-center text-muted-foreground py-10">Loading…</TableCell></TableRow>
            ) : flatCosts.length === 0 ? (
              <TableRow><TableCell colSpan={7} className="text-center text-muted-foreground py-10">No flat costs yet.</TableCell></TableRow>
            ) : (
              flatCosts.map((fc) => (
                <TableRow key={fc.id}>
                  <TableCell className="text-muted-foreground">{fc.property_name} / {fc.apartment_name}</TableCell>
                  <TableCell className="font-medium">{fc.cost_type}</TableCell>
                  <TableCell>{fc.amount.toFixed(2)} €</TableCell>
                  <TableCell className="text-muted-foreground capitalize">{fc.frequency}</TableCell>
                  <TableCell className="text-muted-foreground">{fc.valid_from || "—"}</TableCell>
                  <TableCell className="text-muted-foreground">{fc.valid_to || "—"}</TableCell>
                  <TableCell>
                    <div className="flex gap-1 justify-end">
                      <Button variant="ghost" size="icon" onClick={() => openEdit(fc)}><Pencil className="size-4" /></Button>
                      <Button variant="ghost" size="icon" className="text-destructive hover:text-destructive" onClick={() => remove.mutate(fc.id)}><Trash2 className="size-4" /></Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </Card>

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
