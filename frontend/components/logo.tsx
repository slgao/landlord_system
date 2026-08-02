import { cn } from "@/lib/utils";

// Dachly mark — the roof-gable Λ, identical to the landing page header. Drawn
// in currentColor so it reads as ink in either theme.
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 150 150" className={className} xmlns="http://www.w3.org/2000/svg" aria-hidden fill="currentColor">
      <path d="M75 18 L146 132 L116 132 L75 66 L34 132 L4 132 Z" />
    </svg>
  );
}

// Full lockup: mark + wordmark.
export function Logo({ className }: { className?: string }) {
  return (
    <span className={cn("flex items-center gap-2", className)}>
      <LogoMark className="size-5 shrink-0" />
      <span className="font-semibold text-sm tracking-tight text-foreground">
        Dach<span className="text-primary">ly</span>
      </span>
    </span>
  );
}
