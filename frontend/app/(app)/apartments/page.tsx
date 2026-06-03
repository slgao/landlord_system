"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Apartment, Property } from "@/lib/types";
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
import { ConfirmButton } from "@/components/confirm-button";
import { Pencil, Trash2 } from "lucide-react";

const EMPTY = { property_id: 0, name: "", flat: "" };

export default function ApartmentsPage() {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Apartment | null>(null);
  const [form, setForm] = useState<typeof EMPTY>(EMPTY);
  const [filterProp, setFilterProp] = useState<string>("all");

  const { data: properties = [] } = useQuery<Property[]>({
    queryKey: ["properties"],
    queryFn: () => api.get("/api/properties/").then((r) => r.data),
  });
  const { data: apartments = [], isLoading } = useQuery<Apartment[]>({
    queryKey: ["apartments", filterProp],
    queryFn: () => {
      const params = filterProp !== "all" ? `?property_id=${filterProp}` : "";
      return api.get(`/api/apartments/${params}`).then((r) => r.data);
    },
  });

  const save = useMutation({
    mutationFn: (data: typeof EMPTY) =>
      editing
        ? api.put(`/api/apartments/${editing.id}`, data)
        : api.post("/api/apartments/", data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["apartments"] });
      toast.success(editing ? "Apartment updated" : "Apartment created");
      setOpen(false);
    },
    onError: () => toast.error("Failed to save"),
  });

  const remove = useMutation({
    mutationFn: (id: number) => api.delete(`/api/apartments/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["apartments"] });
      toast.success("Apartment deleted");
    },
    onError: (e: any) =>
      toast.error(e.response?.data?.detail || "Cannot delete"),
  });

  function openCreate() {
    setEditing(null);
    setForm({ ...EMPTY, property_id: Number(filterProp) || 0 });
    setOpen(true);
  }

  function openEdit(a: Apartment) {
    setEditing(a);
    setForm({ property_id: a.property_id, name: a.name, flat: a.flat || "" });
    setOpen(true);
  }

  return (
    <div className="max-w-4xl">
      <PageHeader title="Apartments" action={{ label: "New Apartment", onClick: openCreate }}>
        <Select value={filterProp} onValueChange={setFilterProp}>
          <SelectTrigger className="w-44 h-8 text-sm">
            <SelectValue placeholder="All properties" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All properties</SelectItem>
            {properties.map((p) => (
              <SelectItem key={p.id} value={String(p.id)}>{p.name}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </PageHeader>

      <Card>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Property</TableHead>
              <TableHead>Apartment</TableHead>
              <TableHead>Flat/Unit</TableHead>
              <TableHead className="w-20" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={4} className="text-center text-muted-foreground py-10">Loading…</TableCell>
              </TableRow>
            ) : apartments.length === 0 ? (
              <TableRow>
                <TableCell colSpan={4} className="text-center text-muted-foreground py-10">No apartments yet.</TableCell>
              </TableRow>
            ) : (
              apartments.map((a) => (
                <TableRow key={a.id}>
                  <TableCell className="text-muted-foreground">{a.property_name}</TableCell>
                  <TableCell className="font-medium">{a.name}</TableCell>
                  <TableCell className="text-muted-foreground">{a.flat || "—"}</TableCell>
                  <TableCell>
                    <div className="flex gap-1 justify-end">
                      <Button variant="ghost" size="icon" onClick={() => openEdit(a)}>
                        <Pencil className="size-4" />
                      </Button>
                      <ConfirmButton
                        onConfirm={() => remove.mutate(a.id)}
                        title="Delete apartment?"
                        message={`Delete "${a.name}"? Apartments with contracts can't be deleted.`}
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
            <DialogTitle>{editing ? "Edit Apartment" : "New Apartment"}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1.5">
              <Label>Property</Label>
              <Select
                value={String(form.property_id || "")}
                onValueChange={(v) => setForm((f) => ({ ...f, property_id: Number(v) }))}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select property" />
                </SelectTrigger>
                <SelectContent>
                  {properties.map((p) => (
                    <SelectItem key={p.id} value={String(p.id)}>{p.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Name</Label>
              <Input
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                placeholder="e.g. OG Links"
              />
            </div>
            <div className="space-y-1.5">
              <Label>Flat / Unit</Label>
              <Input
                value={form.flat}
                onChange={(e) => setForm((f) => ({ ...f, flat: e.target.value }))}
                placeholder="e.g. 2B"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button
              onClick={() => save.mutate(form)}
              disabled={!form.name || !form.property_id || save.isPending}
            >
              {save.isPending ? "Saving…" : "Save"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
