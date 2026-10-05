import { PageBody, Section } from "@/components/page-body"
import { SiteHeader } from "@/components/site-header"
import { SourceForm } from "@/components/source-form"
import { createSource } from "@/lib/actions/sources"
import { EMPTY_SOURCE_VALUES } from "@/lib/sources"

export default function NewSourcePage() {
  return (
    <>
      <SiteHeader title="New source" parents={[{ label: "Sources", href: "/sources" }]} />
      <PageBody>
        <Section>
          <SourceForm action={createSource} initialValues={EMPTY_SOURCE_VALUES} submitLabel="Create source" />
        </Section>
      </PageBody>
    </>
  )
}
