import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export function Container({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("mx-auto w-full max-w-5xl px-4 sm:px-6", className)}>{children}</div>;
}

export function PageHeader({ title, lead, children }: { title: string; lead?: string; children?: ReactNode }) {
  return (
    <header className="max-w-3xl space-y-4 pt-12 pb-8 sm:pt-16 sm:pb-10">
      <h1 className="text-4xl leading-[1.05] font-semibold tracking-tight text-balance sm:text-5xl">
        {title}
      </h1>
      {lead ? <p className="max-w-[65ch] text-lg text-pretty text-muted-foreground">{lead}</p> : null}
      {children}
    </header>
  );
}

export function Section({
  title,
  lead,
  action,
  children,
  id,
}: {
  title: string;
  lead?: string;
  action?: ReactNode;
  children: ReactNode;
  id: string;
}) {
  return (
    <section aria-labelledby={id} className="space-y-4 py-8">
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-2">
        <div className="space-y-1">
          <h2 id={id} className="text-xl font-semibold tracking-tight sm:text-2xl">
            {title}
          </h2>
          {lead ? <p className="text-sm text-muted-foreground">{lead}</p> : null}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}
