import { ApplicationStatusForm } from "@/components/application-status-form"
import { ApplicationsList, LongText, parseApplicationParams, type Column } from "@/components/applications-list"
import { api } from "@/lib/api/client"
import type { CommunityApplication } from "@/lib/api/types"
import { formatDateTime } from "@/lib/format"

const columns: Column<CommunityApplication>[] = [
  {
    header: "Name",
    cell: (row) => (
      <div className="grid gap-0.5">
        <span className="font-medium">{row.full_name}</span>
        <span className="text-xs text-muted-foreground">{formatDateTime(row.created_at)}</span>
      </div>
    ),
  },
  {
    header: "Study",
    cell: (row) => (
      <div className="grid gap-0.5 text-sm">
        <span>{row.university ?? "—"}</span>
        <span className="text-muted-foreground">
          {[row.field_of_study, row.year_of_study].filter(Boolean).join(", ") || "—"}
        </span>
      </div>
    ),
  },
  {
    header: "Interests",
    cell: (row) => (
      <div className="grid max-w-56 gap-0.5 text-sm">
        <span>{row.interests.join(", ") || "—"}</span>
        <span className="text-muted-foreground">{row.experience_level ?? ""}</span>
      </div>
    ),
  },
  { header: "Looking for", cell: (row) => <LongText value={row.looking_for} /> },
  {
    header: "Contact",
    cell: (row) => (
      <div className="grid gap-0.5 text-sm">
        <span className="capitalize">{row.preferred_channel}</span>
        <span className="text-muted-foreground">
          {row.preferred_channel === "telegram" ? (row.telegram_username ?? "—") : (row.phone ?? "—")}
        </span>
      </div>
    ),
  },
  { header: "Message", cell: (row) => <LongText value={row.message} /> },
  {
    header: "Consent",
    cell: (row) => (
      <span className="text-xs whitespace-nowrap text-muted-foreground">
        {row.consent_version}, {formatDateTime(row.consented_at)}
      </span>
    ),
  },
  {
    header: "Status",
    cell: (row) => (
      <ApplicationStatusForm
        kind="community"
        id={row.id}
        status={row.status}
        label={`Status of the application from ${row.full_name}`}
      />
    ),
  },
]

export default async function CommunityApplicationsPage({
  searchParams,
}: PageProps<"/community-applications">) {
  const { status, page, query } = parseApplicationParams(await searchParams)
  const result = await api.listCommunityApplications(query)
  return (
    <ApplicationsList
      title="Community Applications"
      path="/community-applications"
      description="Join Community form submissions. Personal data: do not copy it elsewhere."
      status={status}
      page={page}
      result={result}
      columns={columns}
    />
  )
}
