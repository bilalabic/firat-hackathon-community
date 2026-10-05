import { ArrowRight } from "lucide-react";
import type { Metadata } from "next";

import { ExternalLink } from "@/components/external-link";
import { Container, PageHeader } from "@/components/page-shell";
import { about } from "@/lib/copy";
import { externalLinks, routes } from "@/lib/routes";

export const metadata: Metadata = {
  title: about.title,
  description: about.lead,
  alternates: { canonical: routes.about },
};

export default function AboutPage() {
  return (
    <Container>
      <PageHeader title={about.title} lead={about.lead} />
      <div className="max-w-3xl space-y-10">
        <section aria-labelledby="amac" className="space-y-3">
          <h2 id="amac" className="text-xl font-semibold tracking-tight">
            {about.missionTitle}
          </h2>
          <p className="max-w-[65ch]">{about.mission}</p>
        </section>
        <section aria-labelledby="nasil" className="space-y-3">
          <h2 id="nasil" className="text-xl font-semibold tracking-tight">
            {about.howTitle}
          </h2>
          <ul className="max-w-[65ch] list-disc space-y-2 pl-5 marker:text-brand">
            {about.how.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
        <section aria-labelledby="kim" className="space-y-3">
          <h2 id="kim" className="text-xl font-semibold tracking-tight">
            {about.whoTitle}
          </h2>
          <p className="max-w-[65ch]">{about.who}</p>
        </section>
        <section aria-labelledby="iletisim" className="space-y-3">
          <h2 id="iletisim" className="text-xl font-semibold tracking-tight">
            {about.contactTitle}
          </h2>
          <p className="max-w-[65ch]">{about.contact}</p>
          <ExternalLink
            href={`${externalLinks.github}/issues/new`}
            className="inline-flex items-center gap-1 font-medium text-brand hover:underline"
          >
            {about.contactCta}
            <ArrowRight aria-hidden="true" className="size-4" />
          </ExternalLink>
        </section>
      </div>
    </Container>
  );
}
