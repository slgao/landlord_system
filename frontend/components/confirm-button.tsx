"use client";

import { useState, ReactNode } from "react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

interface ConfirmButtonProps {
  onConfirm: () => void;
  title?: string;
  message: string;
  confirmLabel?: string;
  /** the trigger — usually an icon button */
  children: ReactNode;
}

/**
 * Wraps a destructive action in a confirmation dialog so a single misclick
 * can't delete data (especially rows that cascade to children).
 */
export function ConfirmButton({ onConfirm, title = "Are you sure?", message, confirmLabel = "Delete", children }: ConfirmButtonProps) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <span onClick={(e) => { e.stopPropagation(); setOpen(true); }}>{children}</span>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>{title}</DialogTitle></DialogHeader>
          <p className="text-sm text-muted-foreground py-1">{message}</p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button variant="destructive" onClick={() => { onConfirm(); setOpen(false); }}>{confirmLabel}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
