"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Contract, CoTenant } from "@/lib/types";
import { PageHeader } from "@/components/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function MahnungPage() {
  const [contractId, setContractId] = useState("");
  const [amount, setAmount] = useState(0);
  const [customAddress, setCustomAddress] = useState("");
  const [generating, setGenerating] = useState(false);

  const { data: contracts = [] } = useQuery<Contract[]>({
    queryKey: ["contracts-all"],
    queryFn: () => api.get("/api/contracts/").then((r) => r.data),
  });

  const selected = contracts.find((c) => String(c.id) === contractId);

  const { data: coTenants = [] } = useQuery<CoTenant[]>({
    queryKey: ["mahnung-co-tenants", selected?.id],
    queryFn: () => api.get(`/api/co-tenants/?contract_id=${selected!.id}`).then((r) => r.data),
    enabled: !!selected?.id,
  });
  const inContractCoTenants = coTenants.filter((ct) => ct.in_contract);

  async function generate() {
    if (!selected) return;
    setGenerating(true);
    try {
      const token = localStorage.getItem("token");
      const res = await fetch(`${API}/api/reports/mahnung/pdf`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          tenant_name: selected.tenant_name,
          // Leave blank to let the backend resolve the full property address
          // (street + postcode + city) from the contract.
          address: customAddress,
          amount_due: amount,
          contract_id: selected.id,
        }),
      });
      if (!res.ok) { toast.error("Failed to generate PDF"); return; }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `Mahnung_${selected.tenant_name}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success("PDF downloaded");
    } finally {
      setGenerating(false);
    }
  }

  return (
    <div className="max-w-2xl">
      <PageHeader title="Mahnung Generator" description="Generate a payment reminder letter (PDF)" />

      <Card>
        <CardContent className="space-y-4 pt-5">
          <div className="space-y-1.5">
            <Label>Tenant / Contract</Label>
            <Select value={contractId} onValueChange={setContractId}>
              <SelectTrigger><SelectValue placeholder="Select contract" /></SelectTrigger>
              <SelectContent>
                {contracts.map((c) => (
                  <SelectItem key={c.id} value={String(c.id)}>
                    {c.tenant_name} — {c.apartment_name}{c.terminated ? " (terminated)" : ""}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {selected && selected.terminated && (
            <p className="text-xs text-amber-400">⚠ This is an inactive/terminated contract.</p>
          )}
          {selected && (
            <div className="p-3 rounded-md bg-muted/50 text-sm text-muted-foreground space-y-1">
              <p><span className="text-foreground font-medium">{selected.tenant_name}</span></p>
              <p>{selected.apartment_name} · {selected.property_name}</p>
              <p>Monthly rent: {selected.rent.toFixed(2)} {selected.currency}</p>
              {inContractCoTenants.length > 0 && (
                <p className="text-primary">Co-tenants (in contract): {inContractCoTenants.map((c) => c.name).join(", ")}</p>
              )}
            </div>
          )}

          <div className="space-y-1.5">
            <Label>Address (leave blank to use property address)</Label>
            <Input value={customAddress} onChange={(e) => setCustomAddress(e.target.value)} placeholder="Optional manual address override" />
          </div>

          <div className="space-y-1.5">
            <Label>Open Amount (€)</Label>
            <Input type="number" step="0.01" value={amount} onChange={(e) => setAmount(Number(e.target.value))} />
          </div>

          <Button onClick={generate} disabled={!selected || !amount || generating} className="w-full">
            {generating ? "Generating PDF…" : "Generate Mahnung PDF"}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
