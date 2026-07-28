"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
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
};
const EMPTY: Form = { name: "", address: "", building_id: null, we_label: "", mea: "" };

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
    onError: () => toast.error("Failed to save property"),
  });

  const remove = useMutation({
    mutationFn: (id: number) => api.delete(`/api/properties/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["properties"] });
      toast.success("Property deleted");
    },
    onError: (e: any) =>
      toast.error(e.response?.data?.detail || "Cannot delete — apartments exist"),
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
    onError: () => toast.error("Failed to create building"),
  });

  function openCreate() {
    setEditing(null);
    setForm(EMPTY);
    setOpen(true);
  }

  function openEdit(p: Property) {
    setEditing(p);
    setForm({
      name: p.name,
      address: p.address || "",
      building_id: p.building_id ?? null,
      we_label: p.we_label || "",
      mea: p.mea == null ? "" : String(p.mea),
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
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Building</TableHead>
              <TableHead>WE</TableHead>
              <TableHead>MEA</TableHead>
              <TableHead className="w-20" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-muted-foreground py-10">
                  Loading…
                </TableCell>
              </TableRow>
            ) : properties.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-muted-foreground py-10">
                  No properties yet.
                </TableCell>
              </TableRow>
            ) : (
              properties.map((p) => (
                <TableRow key={p.id}>
                  <TableCell className="font-medium">{p.name}</TableCell>
                  <TableCell className="text-muted-foreground">{p.building_name || "—"}</TableCell>
                  <TableCell className="text-muted-foreground">{p.we_label || "—"}</TableCell>
                  <TableCell className="text-muted-foreground font-mono">{p.mea ?? "—"}</TableCell>
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

            <div className="space-y-1.5">
              <Label>Address (legacy / per-WE, optional)</Label>
              <Input
                value={form.address}
                onChange={(e) => setForm((f) => ({ ...f, address: e.target.value }))}
                placeholder="Full address (usually inherited from the building)"
              />
            </div>
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
