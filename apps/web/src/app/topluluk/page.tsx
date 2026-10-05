import type { Metadata } from "next";

import { CommunityForm } from "@/components/forms/community-form";
import { Container, PageHeader } from "@/components/page-shell";
import { community } from "@/lib/copy";
import { routes } from "@/lib/routes";

export const metadata: Metadata = {
  title: community.title,
  description: community.lead,
  alternates: { canonical: routes.community },
};

export default function CommunityPage() {
  return (
    <Container>
      <PageHeader title={community.title} lead={community.lead} />
      <div className="grid gap-12 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
        <div className="space-y-10">
          <section aria-labelledby="neden" className="space-y-3">
            <h2 id="neden" className="text-xl font-semibold tracking-tight">
              {community.whyTitle}
            </h2>
            <ul className="list-disc space-y-2 pl-5 marker:text-brand">
              {community.why.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </section>
          <section aria-labelledby="kanallar" className="space-y-3">
            <h2 id="kanallar" className="text-xl font-semibold tracking-tight">
              {community.channelsTitle}
            </h2>
            <p className="text-muted-foreground">{community.channels}</p>
          </section>
        </div>
        <section aria-labelledby="katil" className="space-y-4">
          <div className="space-y-1">
            <h2 id="katil" className="text-2xl font-semibold tracking-tight">
              {community.formTitle}
            </h2>
            <p className="text-muted-foreground">{community.formLead}</p>
          </div>
          <CommunityForm />
        </section>
      </div>
    </Container>
  );
}
