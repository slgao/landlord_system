"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { logout } from "@/lib/api";
import {
  LayoutDashboard, Building2, Home, Users, FileText,
  CreditCard, DollarSign, Gauge, BarChart3, Bell,
  FileWarning, Zap, Settings, LogOut, ChevronRight,
} from "lucide-react";

const NAV = [
  {
    group: "Overview",
    items: [
      { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
    ],
  },
  {
    group: "Properties",
    items: [
      { href: "/properties", label: "Properties", icon: Building2 },
      { href: "/apartments", label: "Apartments", icon: Home },
    ],
  },
  {
    group: "Tenants",
    items: [
      { href: "/tenants", label: "Tenants", icon: Users },
      { href: "/contracts", label: "Contracts", icon: FileText },
      { href: "/rent-tracking", label: "Rent Tracking", icon: CreditCard },
      { href: "/tenant-ledger", label: "Tenant Ledger", icon: DollarSign },
    ],
  },
  {
    group: "Costs",
    items: [
      { href: "/flat-costs", label: "Flat Costs", icon: DollarSign },
      { href: "/meter-readings", label: "Meter Readings", icon: Gauge },
    ],
  },
  {
    group: "Reports",
    items: [
      { href: "/balance-sheet", label: "Balance Sheet", icon: BarChart3 },
      { href: "/payment-reminders", label: "Payment Reminders", icon: Bell },
      { href: "/nebenkostenabrechnung", label: "Nebenkostenabrechnung", icon: Zap },
      { href: "/mahnung", label: "Mahnung Generator", icon: FileWarning },
    ],
  },
  {
    group: "System",
    items: [
      { href: "/settings", label: "Settings", icon: Settings },
    ],
  },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="flex flex-col w-56 shrink-0 border-r border-border bg-sidebar h-screen sticky top-0">
      {/* Logo */}
      <div className="h-14 flex items-center px-4 border-b border-border">
        <span className="font-semibold text-sm tracking-tight text-foreground">
          Hausverwaltung
        </span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto py-3 px-2">
        {NAV.map((section) => (
          <div key={section.group} className="mb-4">
            <p className="px-2 py-1 text-[10px] font-medium uppercase tracking-widest text-muted-foreground">
              {section.group}
            </p>
            {section.items.map(({ href, label, icon: Icon }) => {
              const active = pathname === href || pathname.startsWith(href + "/");
              return (
                <Link
                  key={href}
                  href={href}
                  className={cn(
                    "flex items-center gap-2.5 px-2 py-1.5 rounded-md text-sm transition-colors",
                    active
                      ? "bg-primary/15 text-primary font-medium"
                      : "text-muted-foreground hover:text-foreground hover:bg-accent"
                  )}
                >
                  <Icon className="size-4 shrink-0" />
                  <span className="truncate">{label}</span>
                  {active && <ChevronRight className="size-3 ml-auto shrink-0 text-primary" />}
                </Link>
              );
            })}
          </div>
        ))}
      </nav>

      {/* Footer */}
      <div className="p-2 border-t border-border">
        <button
          onClick={logout}
          className="flex items-center gap-2.5 w-full px-2 py-1.5 rounded-md text-sm text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
        >
          <LogOut className="size-4" />
          Sign out
        </button>
      </div>
    </aside>
  );
}
