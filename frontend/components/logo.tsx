import { cn } from "@/lib/utils";

// Vermio mark — a solid roof gable (the "wedge") that doubles as the V.
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 150 150" className={className} xmlns="http://www.w3.org/2000/svg" aria-hidden>
      <defs>
        <linearGradient id="vermioMark" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#a5b4fc" />
          <stop offset="100%" stopColor="#6366f1" />
        </linearGradient>
      </defs>
      <path d="M75 18 L146 132 L116 132 L75 66 L34 132 L4 132 Z" fill="url(#vermioMark)" />
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
