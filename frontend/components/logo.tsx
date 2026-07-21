import { cn } from "@/lib/utils";

// Vermio mark — the ledger identity: an ink Λ (roof gable / "V") standing on a
// pine ruled line, on a paper tile. Matches the favicon (app/icon.svg).
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 64 64" className={className} xmlns="http://www.w3.org/2000/svg" aria-hidden>
      <rect width="64" height="64" rx="14" fill="#EFF1EB" />
      <path d="M32 13 L52 49 L42 49 L32 30 L22 49 L12 49 Z" fill="#171C18" />
      <rect x="12" y="52" width="40" height="3" rx="1.5" fill="#1F5D3F" />
    </svg>
  );
}

// Full lockup: mark + wordmark.
export function Logo({ className }: { className?: string }) {
  return (
    <span className={cn("flex items-center gap-2", className)}>
      <LogoMark className="size-5 shrink-0" />
      <span className="font-semibold text-sm tracking-tight text-foreground">
        Ver<span className="text-primary">mio</span>
      </span>
    </span>
  );
}
