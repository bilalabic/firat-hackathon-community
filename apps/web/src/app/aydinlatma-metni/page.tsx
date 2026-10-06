import type { Metadata } from "next";

import { Container, PageHeader } from "@/components/page-shell";
import { type NoticeBlock, PRIVACY_NOTICE_UPDATED, privacyNotice } from "@/lib/privacy";
import { routes } from "@/lib/routes";

export const metadata: Metadata = {
  title: privacyNotice.title,
  description: privacyNotice.lead,
  alternates: { canonical: routes.privacy },
};

export default function PrivacyNoticePage() {
  return (
    <Container>
      <PageHeader title={privacyNotice.title} lead={privacyNotice.lead} />
      <div className="max-w-3xl space-y-10">
        {privacyNotice.sections.map((section) => (
          <section key={section.id} aria-labelledby={section.id} className="space-y-3">
            <h2 id={section.id} className="text-xl font-semibold tracking-tight">
              {section.title}
            </h2>
            {section.blocks.map((block, index) => (
              <Block key={index} block={block} />
            ))}
          </section>
        ))}
        <p className="text-sm text-muted-foreground">Son güncelleme: {PRIVACY_NOTICE_UPDATED}</p>
      </div>
    </Container>
  );
}

function Block({ block }: { block: NoticeBlock }) {
  switch (block.kind) {
    case "p":
      return <p className="max-w-[65ch]">{block.text}</p>;
    case "list":
      return (
        <ul className="max-w-[65ch] list-disc space-y-2 pl-5 marker:text-brand">
          {block.items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      );
    case "table":
      return (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[32rem] border-collapse text-left text-sm">
            <thead>
              <tr className="border-b">
                {block.head.map((cell) => (
                  <th key={cell} scope="col" className="py-2 pr-4 font-medium">
                    {cell}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {block.rows.map((row) => (
                <tr key={row[0]} className="border-b align-top last:border-0">
                  {row.map((cell, index) =>
                    index === 0 ? (
                      <th key={cell} scope="row" className="py-2 pr-4 font-medium">
                        {cell}
                      </th>
                    ) : (
                      <td key={cell} className="py-2 pr-4 text-muted-foreground">
                        {cell}
                      </td>
                    ),
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
  }
}
