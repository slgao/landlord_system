"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, errorMessage } from "@/lib/api";
import { Property, Building } from "@/lib/types";
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
import { toast } from "sonner";
import { ConfirmButton } from "@/components/confirm-button";
import { Pencil, Trash2 } from "lucide-react";

type Form = {
  name: string;
  address: string;
  building_id: number | null;
  we_label: string;
  mea: string;
  market_value: string;
  market_value_date: string;
  owned: boolean;
  living_sqm: string;
  plot_sqm: string;
  comparable_per_sqm: string;
  valuation_note: string;
};
const EMPTY: Form = { name: "", address: "", building_id: null, we_label: "", mea: "",
                      market_value: "", market_value_date: "", owned: true, living_sqm: "",
                      plot_sqm: "", comparable_per_sqm: "", valuation_note: "" };

function buildingLabel(b: Building): string {
  return b.name || [b.street, b.house_no].filter(Boolean).join(" ") || `Building #${b.id}`;
}

export default function PropertiesPage() {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Property | null>(null);
  const [form, setForm] = useState<Form>(EMPTY);
  const [newBuilding, setNewBuilding] = useState("");

  const { data: properties = [], isLoading } = useQuery<Property[]>({
    queryKey: ["properties"],
    queryFn: () => api.get("/api/properties/").then((r) => r.data),
  });
  const { data: buildings = [] } = useQuery<Building[]>({
    queryKey: ["buildings"],
    queryFn: () => api.get("/api/buildings/").then((r) => r.data),
  });

  const save = useMutation({
    mutationFn: (data: Form) => {
      const payload = {
        name: data.name,
        address: data.address || null,
        building_id: data.building_id,
        we_label: data.we_label || null,
        mea: data.mea === "" ? null : parseFloat(data.mea),
        market_value: data.market_value === "" ? null : parseFloat(data.market_value),
        market_value_date: data.market_value_date || null,
        owned: data.owned,
        living_sqm: data.living_sqm === "" ? null : parseFloat(data.living_sqm),
        plot_sqm: data.plot_sqm === "" ? null : parseFloat(data.plot_sqm),
        comparable_per_sqm: data.comparable_per_sqm === "" ? null
          : parseFloat(data.comparable_per_sqm),
        valuation_note: data.valuation_note || null,
      };
      return editing
        ? api.put(`/api/properties/${editing.id}`, payload)
        : api.post("/api/properties/", payload);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["properties"] });
      qc.invalidateQueries({ queryKey: ["buildings"] });
      toast.success(editing ? "Property updated" : "Property created");
      setOpen(false);
    },
    onError: (e) => toast.error(errorMessage(e, "Could not save the property")),
  });

  const remove = useMutation({
    mutationFn: (id: number) => api.delete(`/api/properties/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["properties"] });
      toast.success("Property deleted");
    },
    onError: (e) => toast.error(errorMessage(e, "Cannot delete — apartments exist")),
  });

  // Quick-create a building from the property dialog and select it.
  const createBuilding = useMutation({
    mutationFn: (name: string) =>
      api.post("/api/buildings/", { name }).then((r) => r.data as Building),
    onSuccess: (b) => {
      qc.invalidateQueries({ queryKey: ["buildings"] });
      setForm((f) => ({ ...f, building_id: b.id }));
      setNewBuilding("");
      toast.success("Building created");
    },
    onError: (e) => toast.error(errorMessage(e, "Could not create the building")),
  });

  function openCreate() {
    setEditing(null);
    setForm(EMPTY);
    setOpen(true);
  }

  // An edit must never hide a field that already has something in it.
  const hasValuationData = !!(form.living_sqm || form.comparable_per_sqm
    || form.plot_sqm || form.market_value || form.valuation_note);

  function openEdit(p: Property) {
    setEditing(p);
    setForm({
      name: p.name,
      address: p.address || "",
      building_id: p.building_id ?? null,
      we_label: p.we_label || "",
      mea: p.mea == null ? "" : String(p.mea),
      market_value: p.market_value == null ? "" : String(p.market_value),
      market_value_date: p.market_value_date || "",
      owned: p.owned !== false,
      living_sqm: p.living_sqm == null ? "" : String(p.living_sqm),
      plot_sqm: p.plot_sqm == null ? "" : String(p.plot_sqm),
      comparable_per_sqm: p.comparable_per_sqm == null ? "" : String(p.comparable_per_sqm),
      valuation_note: p.valuation_note || "",
    });
    setOpen(true);
  }

  return (
    <div className="max-w-4xl">
      <PageHeader title="Properties (WEs)" action={{ label: "New Property", onClick: openCreate }} />
      <p className="text-sm text-muted-foreground mb-4">
        Each property is one Wohnungseigentum unit (WE) = one Anlage V. Group several WEs at the
        same address under one <span className="font-medium">building</span>; they stay separate
        tax-declaration units.
      </p>

      <Card>
        <Table className="stack-sm">
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Building</TableHead>
              <TableHead>WE</TableHead>
              <TableHead>MEA</TableHead>
              <TableHead className="text-right">Market value</TableHead>
              <TableHead className="w-20" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-muted-foreground py-10">
                  Loading…
                </TableCell>
              </TableRow>
            ) : properties.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-muted-foreground py-10">
                  No properties yet.
                </TableCell>
              </TableRow>
            ) : (
              properties.map((p) => (
                <TableRow key={p.id}>
                  <TableCell data-label="Name" className="font-medium">{p.name}</TableCell>
                  <TableCell data-label="Building" className="text-muted-foreground">{p.building_name || "—"}</TableCell>
                  <TableCell data-label="WE" className="text-muted-foreground">{p.we_label || "—"}</TableCell>
                  <TableCell data-label="MEA" className="text-muted-foreground font-mono">{p.mea ?? "—"}</TableCell>
                  <TableCell data-label="Market value" className="text-right font-mono">
                    {p.market_value != null ? (
                      <>
                        {p.market_value.toLocaleString("de-DE", { minimumFractionDigits: 0, maximumFractionDigits: 0 })} €
                        {p.market_value_date && (
                          <span className="block text-[10px] text-muted-foreground">{p.market_value_date}</span>
                        )}
                      </>
                    ) : <span className="text-muted-foreground">—</span>}
                  </TableCell>
                  <TableCell>
                    <div className="flex gap-1 justify-end">
                      <Button variant="ghost" size="icon" onClick={() => openEdit(p)}>
                        <Pencil className="size-4" />
                      </Button>
                      <ConfirmButton
                        onConfirm={() => remove.mutate(p.id)}
                        title="Delete property?"
                        message={`Delete "${p.name}"? Properties with apartments can't be deleted.`}
                      >
                        <Button variant="ghost" size="icon" className="text-destructive hover:text-destructive">
                          <Trash2 className="size-4" />
                        </Button>
                      </ConfirmButton>
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
          <DialogHeader>
            <DialogTitle>{editing ? "Edit Property (WE)" : "New Property (WE)"}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1.5">
              <Label>Name</Label>
              <Input
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                placeholder="e.g. Emserstr. 100 – WE 3"
              />
            </div>

            <div className="space-y-1.5">
              <Label>Building</Label>
              <select
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm"
                value={form.building_id ?? ""}
                onChange={(e) =>
                  setForm((f) => ({ ...f, building_id: e.target.value ? Number(e.target.value) : null }))
                }
              >
                <option value="">— No building —</option>
                {buildings.map((b) => (
                  <option key={b.id} value={b.id}>
                    {buildingLabel(b)} {b.unit_count ? `(${b.unit_count} WE)` : ""}
                  </option>
                ))}
              </select>
              <div className="flex gap-2 pt-1">
                <Input
                  value={newBuilding}
                  onChange={(e) => setNewBuilding(e.target.value)}
                  placeholder="…or create a new building by address"
                  className="h-8 text-sm"
                />
                <Button
                  type="button" variant="outline" size="sm"
                  disabled={!newBuilding || createBuilding.isPending}
                  onClick={() => createBuilding.mutate(newBuilding)}
                >
                  Add
                </Button>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label>WE label</Label>
                <Input
                  value={form.we_label}
                  onChange={(e) => setForm((f) => ({ ...f, we_label: e.target.value }))}
                  placeholder="e.g. WE 3"
                />
              </div>
              <div className="space-y-1.5">
                <Label>MEA (Miteigentumsanteil)</Label>
                <Input
                  type="number" step="0.0001"
                  value={form.mea}
                  onChange={(e) => setForm((f) => ({ ...f, mea: e.target.value }))}
                  placeholder="e.g. 0.25"
                />
              </div>
            </div>

            {/* Whether the flat is yours at all. A managed flat is tracked
                like any other, but its worth is not your asset — so this
                decides whether the rest of this block means anything. */}
            <div className="rounded-lg border border-border p-3">
              <label className="flex items-center gap-2 text-sm font-medium">
                <input
                  type="checkbox" className="size-4 accent-primary"
                  checked={form.owned}
                  onChange={(e) => setForm((f) => ({ ...f, owned: e.target.checked }))}
                />
                I own this flat
              </label>
              <p className="mt-1 text-xs text-muted-foreground">
                {form.owned
                  ? "Counted in the portfolio value, the equity and the LTV."
                  : "Managed but not owned — tracked like any other flat, but left out of the valuation and every total."}
              </p>
            </div>

            {form.owned && (
            <details className="rounded-lg border border-border" open={hasValuationData}>
              {/* Twelve fields for a first property is a wall. The four that
                  identify the flat stay in front; what the valuation needs
                  waits behind this, open already when there is something in
                  it so an edit never hides a filled-in field. */}
              <summary className="cursor-pointer select-none p-3 text-sm font-medium">
                Valuation data
                <span className="ml-2 font-normal text-muted-foreground text-xs">
                  Wohnfläche, comparable €/m², market value — needed for the
                  portfolio value and the LTV
                </span>
              </summary>
              <div className="space-y-3 border-t border-border p-3">

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="p-mv">Market value (€)</Label>
                <Input
                  type="number" step="1000" min="0"
                  id="p-mv" value={form.market_value}
                  onChange={(e) => setForm((f) => ({ ...f, market_value: e.target.value }))}
                  placeholder="e.g. 210000"
                />
                <p className="text-xs text-muted-foreground">
                  Equity is this less the debt. Only the purchase price is otherwise on file.
                </p>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="p-mvd">Valued on</Label>
                <Input
                  type="date"
                  id="p-mvd" value={form.market_value_date}
                  onChange={(e) => setForm((f) => ({ ...f, market_value_date: e.target.value }))}
                />
                <p className="text-xs text-muted-foreground">When the estimate was made.</p>
              </div>
            </div>

            <div className="grid grid-cols-3 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="p-living">Living area (m²)</Label>
                <Input
                  type="number" step="0.01" min="0"
                  id="p-living" value={form.living_sqm}
                  onChange={(e) => setForm((f) => ({ ...f, living_sqm: e.target.value }))}
                  placeholder="e.g. 49"
                />
                <p className="text-xs text-muted-foreground">
                  The flat&apos;s Wohnfläche — a WG&apos;s rooms do not add up to it.
                </p>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="p-comp">Comparable (€/m²)</Label>
                <Input
                  type="number" step="50" min="0"
                  id="p-comp" value={form.comparable_per_sqm}
                  onChange={(e) => setForm((f) => ({ ...f, comparable_per_sqm: e.target.value }))}
                  placeholder="e.g. 5400"
                />
                <p className="text-xs text-muted-foreground">
                  What similar flats fetch. The Gutachterausschuss publishes these per district.
                </p>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="p-plot">Plot area (m²)</Label>
                <Input
                  type="number" step="1" min="0"
                  id="p-plot" value={form.plot_sqm}
                  onChange={(e) => setForm((f) => ({ ...f, plot_sqm: e.target.value }))}
                  placeholder="optional"
                />
                <p className="text-xs text-muted-foreground">
                  With the MEA this gives the exact land share.
                </p>
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="p-vnote">Valuation note</Label>
              <Input
                id="p-vnote" value={form.valuation_note}
                onChange={(e) => setForm((f) => ({ ...f, valuation_note: e.target.value }))}
                placeholder="Where the comparable came from, e.g. Immobilienmarktbericht 2024/2025"
              />
            </div>

              </div>
            </details>
            )}

            {/* The building carries the address; this is the per-WE override,
                for the rare flat whose address differs from its building's. */}
            <details className="rounded-lg border border-border" open={!!form.address}>
              <summary className="cursor-pointer select-none p-3 text-sm font-medium">
                Own address
                <span className="ml-2 font-normal text-muted-foreground text-xs">
                  only when it differs from the building&apos;s
                </span>
              </summary>
              <div className="border-t border-border p-3 space-y-1.5">
                <Label htmlFor="p-addr">Address</Label>
                <Input
                  id="p-addr" value={form.address}
                  onChange={(e) => setForm((f) => ({ ...f, address: e.target.value }))}
                  placeholder="Full address (usually inherited from the building)"
                />
              </div>
            </details>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button onClick={() => save.mutate(form)} disabled={!form.name || save.isPending}>
              {save.isPending ? "Saving…" : "Save"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
