"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Property } from "@/lib/types";
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

const EMPTY = { name: "", address: "" };

export default function PropertiesPage() {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Property | null>(null);
  const [form, setForm] = useState(EMPTY);

  const { data: properties = [], isLoading } = useQuery<Property[]>({
    queryKey: ["properties"],
    queryFn: () => api.get("/api/properties/").then((r) => r.data),
  });

  const save = useMutation({
    mutationFn: (data: typeof EMPTY) =>
      editing
        ? api.put(`/api/properties/${editing.id}`, data)
        : api.post("/api/properties/", data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["properties"] });
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

  function openCreate() {
    setEditing(null);
    setForm(EMPTY);
    setOpen(true);
  }

  function openEdit(p: Property) {
    setEditing(p);
    setForm({ name: p.name, address: p.address || "" });
    setOpen(true);
  }

  return (
    <div className="max-w-4xl">
      <PageHeader title="Properties" action={{ label: "New Property", onClick: openCreate }} />

      <Card>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Address</TableHead>
              <TableHead className="w-20" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={3} className="text-center text-muted-foreground py-10">
                  Loading…
                </TableCell>
              </TableRow>
            ) : properties.length === 0 ? (
              <TableRow>
                <TableCell colSpan={3} className="text-center text-muted-foreground py-10">
                  No properties yet.
                </TableCell>
              </TableRow>
            ) : (
              properties.map((p) => (
                <TableRow key={p.id}>
                  <TableCell className="font-medium">{p.name}</TableCell>
                  <TableCell className="text-muted-foreground">{p.address || "—"}</TableCell>
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
            <DialogTitle>{editing ? "Edit Property" : "New Property"}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1.5">
              <Label>Name</Label>
              <Input
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                placeholder="e.g. Musterstraße 1"
              />
            </div>
            <div className="space-y-1.5">
              <Label>Address</Label>
              <Input
                value={form.address}
                onChange={(e) => setForm((f) => ({ ...f, address: e.target.value }))}
                placeholder="Full address"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button
              onClick={() => save.mutate(form)}
              disabled={!form.name || save.isPending}
            >
              {save.isPending ? "Saving…" : "Save"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
