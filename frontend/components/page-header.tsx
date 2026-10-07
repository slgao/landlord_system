import { ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Plus } from "lucide-react";

interface Props {
  title: string;
  description?: string;
  action?: { label: string; onClick: () => void };
  children?: ReactNode;
}

export function PageHeader({ title, description, action, children }: Props) {
  return (
    // Wraps rather than forcing the page wider than the screen: a title plus a
    // search box and an action button do not fit on a phone in one row.
    <div className="flex flex-wrap items-start justify-between gap-3 mb-6">
      <div>
        <h1 className="font-display text-2xl font-extrabold tracking-tight">{title}</h1>
        {description && (
          <p className="text-sm text-muted-foreground mt-1">{description}</p>
        )}
      </div>
      <div className="flex items-center gap-2">
        {children}
        {action && (
          <Button size="sm" onClick={action.onClick}>
            <Plus className="size-4 mr-1" />
            {action.label}
          </Button>
        )}
      </div>
    </div>
  );
}
