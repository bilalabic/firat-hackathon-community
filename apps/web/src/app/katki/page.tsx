import { ArrowRight } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

import { ExternalLink } from "@/components/external-link";
import { TeamForm } from "@/components/forms/team-form";
import { Container, PageHeader } from "@/components/page-shell";
import { contribute } from "@/lib/copy";
import { externalLinks, routes } from "@/lib/routes";

export const metadata: Metadata = {
  title: contribute.title,
  description: contribute.lead,
  alternates: { canonical: routes.contribute },
};

const linkClass = "inline-flex items-center gap-1 font-medium text-brand hover:underline";

function Intent({ id, title, lead, children }: { id: string; title: string; lead: string; children?: ReactNode }) {
  return (
    <section aria-labelledby={id} className="space-y-3 py-8">
      <h2 id={id} className="text-xl font-semibold tracking-tight">
        {title}
      </h2>
      <p className="max-w-[65ch] text-muted-foreground">{lead}</p>
      {children}
    </section>
  );
}

export default function ContributePage() {
  return (
    <Container>
      <PageHeader title={contribute.title} lead={contribute.lead} />
      <div className="grid gap-x-12 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
        <div className="divide-y border-y lg:self-start">
          <Intent id="kod" title={contribute.code.title} lead={contribute.code.lead}>
            <ul className="space-y-2">
              <li>
                <ExternalLink href={externalLinks.github} className={linkClass}>
                  {contribute.code.repo}
                  <ArrowRight aria-hidden="true" className="size-4" />
                </ExternalLink>
              </li>
              <li>
                <ExternalLink href={externalLinks.goodFirstIssues} className={linkClass}>
                  {contribute.code.issues}
                  <ArrowRight aria-hidden="true" className="size-4" />
                </ExternalLink>
              </li>
            </ul>
          </Intent>
          <Intent id="destek" title={contribute.support.title} lead={contribute.support.lead} />
          <Intent id="etkinlik-oner" title={contribute.suggest.title} lead={contribute.suggest.lead}>
            <Link href={routes.community} className={linkClass}>
              {contribute.suggest.cta}
              <ArrowRight aria-hidden="true" className="size-4" />
            </Link>
          </Intent>
        </div>
        <section aria-labelledby="ekibe-katil" className="space-y-4 py-8">
          <div className="space-y-1">
            <h2 id="ekibe-katil" className="text-2xl font-semibold tracking-tight">
              {contribute.team.title}
            </h2>
            <p className="text-muted-foreground">{contribute.team.lead}</p>
          </div>
          <TeamForm />
        </section>
      </div>
    </Container>
  );
}
