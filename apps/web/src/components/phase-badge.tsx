import { deadlineCountdown, phaseLabels } from "@/lib/copy";
import type { PhaseInfo } from "@/lib/phase";
import { cn } from "@/lib/utils";

const base = "inline-flex h-6 items-center gap-1.5 rounded-full px-2.5 text-xs font-medium whitespace-nowrap";

export function PhaseBadge({ phase, className }: { phase: PhaseInfo; className?: string }) {
  if (phase.phase === "open" && phase.closingSoon && phase.daysLeft !== null) {
    return (
      <span className={cn(base, "bg-soon-soft text-soon", className)}>
        <span aria-hidden="true" className="size-1.5 rounded-full bg-current" />
        {deadlineCountdown(phase.daysLeft)}
      </span>
    );
  }
  if (phase.phase === "open") {
    return (
      <span className={cn(base, "bg-open-soft text-open", className)}>
        <span aria-hidden="true" className="size-1.5 rounded-full bg-current" />
        {phaseLabels.open}
      </span>
    );
  }
  if (phase.phase === "upcoming") {
    return <span className={cn(base, "bg-secondary text-foreground", className)}>{phaseLabels.upcoming}</span>;
  }
  return <span className={cn(base, "bg-muted text-muted-foreground", className)}>{phaseLabels.past}</span>;
}
