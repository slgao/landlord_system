"use client";

import { useState, ReactNode } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface GroupCardProps {
  title: string;
  subtitle?: string;
  /** right-aligned summary chips, e.g. counts or totals */
  summary?: ReactNode;
  defaultOpen?: boolean;
  children: ReactNode;
}

/** A collapsible card used to group rows under a property / apartment heading. */
export function GroupCard({ title, subtitle, summary, defaultOpen = true, children }: GroupCardProps) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <Card className="overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-4 py-3 text-left hover:bg-muted/20 transition-colors"
      >
        <div className="flex items-center gap-2.5 min-w-0">
          {open ? <ChevronDown className="size-4 shrink-0 text-muted-foreground" />
                : <ChevronRight className="size-4 shrink-0 text-muted-foreground" />}
          <div className="min-w-0">
            <p className="font-medium truncate">{title}</p>
            {subtitle && <p className="text-xs text-muted-foreground truncate">{subtitle}</p>}
          </div>
        </div>
        {summary && <div className="flex items-center gap-2 shrink-0 ml-3">{summary}</div>}
      </button>
      <div className={cn("border-t border-border", open ? "block" : "hidden")}>
        {children}
      </div>
    </Card>
  );
}
