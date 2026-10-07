"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, errorMessage } from "@/lib/api";
import { matchesQuery } from "@/lib/search";
import { Tenant } from "@/lib/types";
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
import { SearchInput } from "@/components/search-input";
import { Pencil, Trash2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";

const EMPTY = { name: "", email: "", phone: "", gender: "diverse" };

export default function TenantsPage() {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Tenant | null>(null);
  const [form, setForm] = useState(EMPTY);
  const [query, setQuery] = useState("");

  const { data: tenants = [], isLoading } = useQuery<Tenant[]>({
    queryKey: ["tenants"],
    queryFn: () => api.get("/api/tenants/").then((r) => r.data),
  });

  const save = useMutation({
    mutationFn: (data: typeof EMPTY) =>
      editing
        ? api.put(`/api/tenants/${editing.id}`, data)
        : api.post("/api/tenants/", data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tenants"] });
      toast.success(editing ? "Tenant updated" : "Tenant created");
      setOpen(false);
    },
    onError: (e) => toast.error(errorMessage(e, "Could not save the tenant")),
  });

  const remove = useMutation({
    mutationFn: (id: number) => api.delete(`/api/tenants/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tenants"] });
      toast.success("Tenant deleted");
    },
    onError: (e) => toast.error(errorMessage(e, "Cannot delete — contracts exist")),
  });

  function openCreate() { setEditing(null); setForm(EMPTY); setOpen(true); }
  function openEdit(t: Tenant) {
    setEditing(t);
    setForm({ name: t.name, email: t.email || "", phone: t.phone || "", gender: t.gender });
    setOpen(true);
  }

  const genderLabel = (g: string) =>
    g === "male" ? "Herr" : g === "female" ? "Frau" : "Divers";

  const visible = tenants.filter((t) => matchesQuery(query, [
    t.name, t.email, t.phone, genderLabel(t.gender),
    // Searching the flat finds who lives there.
    ...(t.renting ?? []).flatMap((r) => [r.property_name, r.apartment_name]),
  ]));

  // Everyone on file, past and present: a tenant row outlives the contract,
  // so this is how many people have rented from you. Counted over all of
  // them, not the search result.
  const byGender = tenants.reduce((acc, t) => {
    const key = t.gender === "male" || t.gender === "female" ? t.gender : "diverse";
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {} as Record<"male" | "female" | "diverse", number>);
  const share = (n: number) => (tenants.length ? Math.round((n / tenants.length) * 100) : 0);
  const renting = tenants.filter((t) => (t.active_contracts ?? 0) > 0).length;

  return (
    <div className="max-w-4xl">
      <PageHeader title="Tenants" action={{ label: "New Tenant", onClick: openCreate }}>
        <SearchInput value={query} onChange={setQuery} placeholder="Search name, email, phone…" className="w-full sm:w-64" />
      </PageHeader>

      <Card className="mb-4 p-4">
        <div className="flex flex-wrap items-end gap-x-10 gap-y-3">
          <div>
            <p className="text-xs text-muted-foreground uppercase tracking-wide">Tenants in total</p>
            <p className="text-2xl font-semibold mt-0.5">{tenants.length}</p>
            <p className="text-xs text-muted-foreground">past and present</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground uppercase tracking-wide">Currently renting</p>
            <p className="text-2xl font-semibold mt-0.5 text-primary">{renting}</p>
            <p className="text-xs text-muted-foreground">
              {/* "no longer" would be wrong for someone who never rented, and
                  for a contract that starts next month. */}
              {tenants.length - renting} not renting now
            </p>
          </div>
          {([["male", "Herr"], ["female", "Frau"], ["diverse", "Divers"]] as const).map(([key, label]) => (
            <div key={key}>
              <p className="text-xs text-muted-foreground uppercase tracking-wide">{label}</p>
              <p className="text-xl font-medium mt-0.5">
                {byGender[key] || 0}
                <span className="text-xs text-muted-foreground font-normal ml-1.5">
                  {share(byGender[key] || 0)}%
                </span>
              </p>
            </div>
          ))}
          {query && (
            <p className="text-xs text-muted-foreground ml-auto">
              {visible.length} of {tenants.length} match &ldquo;{query}&rdquo;
            </p>
          )}
        </div>
      </Card>

      <Card>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Email</TableHead>
              <TableHead>Phone</TableHead>
              <TableHead>Salutation</TableHead>
              <TableHead className="w-20" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-muted-foreground py-10">Loading…</TableCell>
              </TableRow>
            ) : visible.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-muted-foreground py-10">
                  {tenants.length === 0 ? "No tenants yet." : <>No tenants match &ldquo;{query}&rdquo;.</>}
                </TableCell>
              </TableRow>
            ) : (
              visible.map((t) => (
                <TableRow key={t.id}>
                  <TableCell className="font-medium">
                    {t.name}
                    {(t.active_contracts ?? 0) > 0 && (
                      <Badge className="ml-2 bg-primary/15 text-primary border-primary/20"
                        title="Has a contract running today">
                        Renting{(t.active_contracts ?? 0) > 1 ? ` ×${t.active_contracts}` : ""}
                      </Badge>
                    )}
                    {/* Which flat, so the badge says who and where. */}
                    {(t.renting ?? []).map((r) => (
                      <span key={r.contract_id} className="block text-xs font-normal text-muted-foreground">
                        {r.property_name} · {r.apartment_name}
                        {r.end_date ? ` · until ${r.end_date}` : ""}
                      </span>
                    ))}
                  </TableCell>
                  <TableCell className="text-muted-foreground">{t.email || "—"}</TableCell>
                  <TableCell className="text-muted-foreground">
                    {t.phone ? <a href={`tel:${t.phone}`} className="hover:underline">{t.phone}</a> : "—"}
                  </TableCell>
                  <TableCell className="text-muted-foreground">{genderLabel(t.gender)}</TableCell>
                  <TableCell>
                    <div className="flex gap-1 justify-end">
                      <Button variant="ghost" size="icon" onClick={() => openEdit(t)}>
                        <Pencil className="size-4" />
                      </Button>
                      <ConfirmButton
                        onConfirm={() => remove.mutate(t.id)}
                        title="Delete tenant?"
                        message={`Delete "${t.name}"? Tenants with contracts can't be deleted.`}
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
        {query && visible.length > 0 && (
          <p className="px-4 py-2 text-xs text-muted-foreground border-t border-border">
            {visible.length} of {tenants.length} tenants
          </p>
        )}
      </Card>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editing ? "Edit Tenant" : "New Tenant"}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1.5">
              <Label>Full Name</Label>
              <Input
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                placeholder="Max Mustermann"
              />
            </div>
            <div className="space-y-1.5">
              <Label>Email</Label>
              <Input
                type="email"
                value={form.email}
                onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
                placeholder="max@example.com"
              />
            </div>
            <div className="space-y-1.5">
              <Label>Phone</Label>
              <Input
                type="tel"
                value={form.phone}
                onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))}
                placeholder="+49 170 1234567"
              />
            </div>
            <div className="space-y-1.5">
              <Label>Gender / Salutation</Label>
              <Select value={form.gender} onValueChange={(v) => setForm((f) => ({ ...f, gender: v }))}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="male">Herr (male)</SelectItem>
                  <SelectItem value="female">Frau (female)</SelectItem>
                  <SelectItem value="diverse">Divers</SelectItem>
                </SelectContent>
              </Select>
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
