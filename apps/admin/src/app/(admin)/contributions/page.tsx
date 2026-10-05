import { ApplicationStatusForm } from "@/components/application-status-form"
import { ApplicationsList, LongText, parseApplicationParams, type Column } from "@/components/applications-list"
import { ExternalLink } from "@/components/external-link"
import { api } from "@/lib/api/client"
import type { TeamApplication } from "@/lib/api/types"
import { formatDateTime } from "@/lib/format"

const columns: Column<TeamApplication>[] = [
  {
    header: "Name",
    cell: (row) => (
      <div className="grid gap-0.5">
        <span className="font-medium">{row.full_name}</span>
        <span className="text-xs text-muted-foreground">{formatDateTime(row.created_at)}</span>
      </div>
    ),
  },
  { header: "Affiliation", cell: (row) => row.affiliation ?? "—" },
  {
    header: "Areas",
    cell: (row) => <span className="block max-w-48 text-sm">{row.areas.join(", ") || "—"}</span>,
  },
  { header: "Skills", cell: (row) => <LongText value={row.skills} /> },
  {
    header: "Links",
    cell: (row) => (
      <div className="grid gap-0.5 text-sm">
        {row.github_url && <ExternalLink href={row.github_url}>GitHub</ExternalLink>}
        {row.linkedin_url && <ExternalLink href={row.linkedin_url}>LinkedIn</ExternalLink>}
        {!row.github_url && !row.linkedin_url && <span className="text-muted-foreground">—</span>}
      </div>
    ),
  },
  { header: "Availability", cell: (row) => <LongText value={row.availability} /> },
  { header: "Motivation", cell: (row) => <LongText value={row.motivation} /> },
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
        kind="team"
        id={row.id}
        status={row.status}
        label={`Status of the application from ${row.full_name}`}
      />
    ),
  },
]

export default async function ContributionsPage({ searchParams }: PageProps<"/contributions">) {
  const { status, page, query } = parseApplicationParams(await searchParams)
  const result = await api.listTeamApplications(query)
  return (
    <ApplicationsList
      title="Contributions"
      path="/contributions"
      description="Team applications from the Contribute form. Personal data: do not copy it elsewhere."
      status={status}
      page={page}
      result={result}
      columns={columns}
    />
  )
}
