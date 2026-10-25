"use client";

/**
 * ⌘K — find a tenant, a flat, a property or a page by typing its name.
 *
 * The sidebar lists twenty-one pages in eight groups, and the thing a
 * landlord is usually after is not a page at all but a person: "what is
 * Anna's deposit". Scanning a list of pages for that costs more than typing
 * four letters.
 */

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Apartment, Contract, Property, Tenant } from "@/lib/types";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Building2, FileText, Home, Search, Users } from "lucide-react";

type Hit = { id: string; label: string; sub?: string; href: string; icon: React.ElementType };

const PAGES: Hit[] = [
  { id: "p-dashboard", label: "Dashboard", href: "/dashboard", icon: Search },
  { id: "p-properties", label: "Properties", href: "/properties", icon: Building2 },
  { id: "p-apartments", label: "Apartments", href: "/apartments", icon: Home },
  { id: "p-tenants", label: "Tenants", href: "/tenants", icon: Users },
  { id: "p-contracts", label: "Contracts", href: "/contracts", icon: FileText },
  { id: "p-rent", label: "Rent Tracking", href: "/rent-tracking", icon: FileText },
  { id: "p-ledger", label: "Tenant Ledger", href: "/tenant-ledger", icon: FileText },
  { id: "p-costs", label: "Flat Costs", href: "/flat-costs", icon: FileText },
  { id: "p-meters", label: "Meter Readings", href: "/meter-readings", icon: FileText },
  { id: "p-balance", label: "Balance Sheet", href: "/balance-sheet", icon: FileText },
  { id: "p-financing", label: "Financing", href: "/financing", icon: FileText },
  { id: "p-valuation", label: "Valuation", href: "/valuation", icon: FileText },
  { id: "p-econ", label: "Flat Economics", href: "/flat-economics", icon: FileText },
  { id: "p-reminders", label: "Payment Reminders", href: "/payment-reminders", icon: FileText },
  { id: "p-nk", label: "Nebenkostenabrechnung", href: "/nebenkostenabrechnung", icon: FileText },
  { id: "p-nks", label: "NK Settlements", href: "/nk-settlements", icon: FileText },
  { id: "p-mahnung", label: "Mahnung Generator", href: "/mahnung", icon: FileText },
  { id: "p-taxsetup", label: "Tax Setup", href: "/tax-setup", icon: FileText },
  { id: "p-tax", label: "Tax Report", href: "/tax", icon: FileText },
  { id: "p-ask", label: "Ask Dachly", href: "/ask", icon: FileText },
  { id: "p-settings", label: "Settings", href: "/settings", icon: FileText },
];

const norm = (s: string) => s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");

export function CommandSearch() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [active, setActive] = useState(0);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => !v);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Only once the dialog is open: a landlord who never presses ⌘K should not
  // pay four requests for the privilege.
  const { data: tenants = [] } = useQuery<Tenant[]>({
    queryKey: ["tenants"], enabled: open,
    queryFn: () => api.get("/api/tenants/").then((r) => r.data),
  });
  const { data: properties = [] } = useQuery<Property[]>({
    queryKey: ["properties"], enabled: open,
    queryFn: () => api.get("/api/properties/").then((r) => r.data),
  });
  const { data: apartments = [] } = useQuery<Apartment[]>({
    queryKey: ["apartments"], enabled: open,
    queryFn: () => api.get("/api/apartments/").then((r) => r.data),
  });
  const { data: contracts = [] } = useQuery<Contract[]>({
    queryKey: ["contracts-all"], enabled: open,
    queryFn: () => api.get("/api/contracts/").then((r) => r.data),
  });

  const hits = useMemo(() => {
    const all: Hit[] = [
      ...tenants.map((t) => ({ id: `t${t.id}`, label: t.name, sub: t.email || "Tenant",
                               href: "/tenant-ledger", icon: Users })),
      ...contracts.map((c) => ({ id: `c${c.id}`, label: c.tenant_name ?? "Tenancy",
                                 sub: `${c.apartment_name ?? ""} · tenancy`,
                                 href: "/contracts", icon: FileText })),
      ...properties.map((p) => ({ id: `p${p.id}`, label: p.name, sub: p.address || "Property",
                                  href: "/properties", icon: Building2 })),
      ...apartments.map((a) => ({ id: `a${a.id}`, label: a.name,
                                  sub: `${a.property_name ?? ""} · flat`,
                                  href: "/apartments", icon: Home })),
      ...PAGES,
    ];
    if (!q.trim()) return PAGES.slice(0, 8);
    const needle = norm(q);
    return all.filter((h) => norm(h.label).includes(needle)
                          || norm(h.sub ?? "").includes(needle)).slice(0, 12);
  }, [q, tenants, properties, apartments, contracts]);

  function go(h: Hit) {
    setOpen(false);
    setQ("");
    router.push(h.href);
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="max-w-lg p-0 gap-0 overflow-hidden">
        <DialogTitle className="sr-only">Search</DialogTitle>
        <div className="flex items-center gap-2 border-b border-border px-3">
          <Search className="size-4 text-muted-foreground shrink-0" />
          <Input
            autoFocus value={q}
            onChange={(e) => { setQ(e.target.value); setActive(0); }}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") { e.preventDefault(); setActive((i) => Math.min(i + 1, hits.length - 1)); }
              if (e.key === "ArrowUp") { e.preventDefault(); setActive((i) => Math.max(i - 1, 0)); }
              if (e.key === "Enter" && hits[active]) { e.preventDefault(); go(hits[active]); }
            }}
            placeholder="Tenant, flat, property or page…"
            aria-label="Search tenants, flats, properties and pages"
            className="border-0 shadow-none focus-visible:ring-0 px-0 h-11"
          />
        </div>
        <ul className="max-h-80 overflow-y-auto py-1">
          {hits.length === 0 ? (
            <li className="px-3 py-6 text-center text-sm text-muted-foreground">
              Nothing matches “{q}”.
            </li>
          ) : hits.map((h, i) => (
            <li key={h.id}>
              <button
                onClick={() => go(h)}
                onMouseEnter={() => setActive(i)}
                className={`w-full text-left px-3 py-2 flex items-center gap-3 text-sm
                  ${i === active ? "bg-accent" : ""}`}
              >
                <h.icon className="size-4 text-muted-foreground shrink-0" />
                <span className="min-w-0 flex-1 truncate">{h.label}</span>
                {h.sub && <span className="text-xs text-muted-foreground truncate max-w-[45%]">{h.sub}</span>}
              </button>
            </li>
          ))}
        </ul>
      </DialogContent>
    </Dialog>
  );
}

/** The button in the sidebar that says the shortcut exists. */
export function CommandSearchTrigger() {
  return (
    <button
      onClick={() => window.dispatchEvent(new KeyboardEvent("keydown",
        { key: "k", metaKey: true, bubbles: true }))}
      className="mx-2 mb-2 flex items-center gap-2 rounded-md border border-border
        px-2 py-1.5 text-xs text-muted-foreground hover:text-foreground w-[calc(100%-1rem)]"
    >
      <Search className="size-3.5" />
      <span className="flex-1 text-left">Search…</span>
      <kbd className="font-mono text-[10px] opacity-70">⌘K</kbd>
    </button>
  );
}
