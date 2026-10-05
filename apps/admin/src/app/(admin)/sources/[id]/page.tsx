import { notFound } from "next/navigation"

import { ApiErrorState } from "@/components/api-error-state"
import { PageBody, Section } from "@/components/page-body"
import { SiteHeader } from "@/components/site-header"
import { SourceForm } from "@/components/source-form"
import { updateSource } from "@/lib/actions/sources"
import { api } from "@/lib/api/client"
import { isUuid } from "@/lib/params"
import { sourceToFormValues } from "@/lib/sources"

export default async function EditSourcePage({ params }: PageProps<"/sources/[id]">) {
  const { id } = await params
  if (!isUuid(id)) notFound()
  // The API has no GET /sources/{id}; the list is small (one row per platform).
  const result = await api.listSources()
  const source = result.ok ? result.data.find((item) => item.id === id) : undefined
  if (result.ok && !source) notFound()

  const parents = [{ label: "Sources", href: "/sources" }]
  return (
    <>
      <SiteHeader title={source?.name ?? "Source"} parents={parents} />
      <PageBody>
        <Section>
          {!result.ok ? (
            <ApiErrorState error={result.error} />
          ) : (
            source && (
              <SourceForm
                action={updateSource.bind(null, source.id)}
                initialValues={sourceToFormValues(source)}
                submitLabel="Save changes"
              />
            )
          )}
        </Section>
      </PageBody>
    </>
  )
}
