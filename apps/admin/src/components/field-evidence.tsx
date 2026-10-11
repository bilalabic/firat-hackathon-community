// Field evidence of the latest URL import (GET /events/{id}/evidence, V1.2): per field the
// proposed value, where it came from, the supporting snippet and the extraction flags.
// Rendered only for imported events.

import { TriangleAlertIcon } from "lucide-react"

import { ApiErrorState } from "@/components/api-error-state"
import { ExternalLink } from "@/components/external-link"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { api } from "@/lib/api/client"
import type { Evidence, FieldEvidence } from "@/lib/api/types"
import { formatDateTime } from "@/lib/format"
import {
  FLAG_HINTS,
  FLAG_LABELS,
  SOURCE_HINTS,
  SOURCE_LABELS,
  displayValue,
  fieldLabel,
  runDetails,
  summarizeEvidence,
} from "@/lib/imports"

function FieldItem({ item }: { item: FieldEvidence }) {
  return (
    <li className="grid gap-2 py-3">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-medium">{fieldLabel(item.field)}</span>
        {item.source && (
          <Badge variant="secondary" title={SOURCE_HINTS[item.source]}>
            {SOURCE_LABELS[item.source]}
          </Badge>
        )}
        {item.matches_current === false && (
          <Badge variant="outline" className="text-muted-foreground">
            Edited since import
          </Badge>
        )}
      </div>
      {item.value_text !== null ? (
        <p className="text-sm break-words whitespace-pre-line">{displayValue(item.field, item.value_text)}</p>
      ) : (
        <p className="text-sm text-muted-foreground">No value kept.</p>
      )}
      {item.snippet && (
        <blockquote className="border-l-2 pl-3 text-xs break-words whitespace-pre-line text-muted-foreground">
          {item.snippet}
          {item.extracted_by && item.extracted_by !== item.source && (
            <span className="mt-1 block">({item.extracted_by})</span>
          )}
        </blockquote>
      )}
      {item.flags.map((flag, index) => (
        <Alert key={`${flag.kind}-${index}`} variant="warning">
          <TriangleAlertIcon />
          <AlertTitle>{FLAG_LABELS[flag.kind]}</AlertTitle>
          <AlertDescription>
            <p>{flag.detail}</p>
            <p className="text-xs">{FLAG_HINTS[flag.kind]}</p>
          </AlertDescription>
        </Alert>
      ))}
    </li>
  )
}

function EvidenceDetails({ evidence }: { evidence: Evidence }) {
  const details = runDetails(evidence)
  const summary = summarizeEvidence(evidence.fields)
  const flagText = Object.entries(summary.flags)
    .map(([kind, count]) => `${count} ${FLAG_LABELS[kind as keyof typeof FLAG_LABELS].toLowerCase()}`)
    .join(", ")
  return (
    <div className="grid gap-3">
      <p className="text-sm text-muted-foreground">
        {summary.proposed} {summary.proposed === 1 ? "value" : "values"} proposed
        {summary.flagged > 0 && `, ${summary.flagged} ${summary.flagged === 1 ? "field" : "fields"} flagged (${flagText})`}
        {summary.editedSinceImport > 0 && `, ${summary.editedSinceImport} edited since the import`}.
        {details.extractedBy ? ` Extracted by ${details.extractedBy}.` : " Structured data only."}
        {details.seconds !== null && ` Took ${details.seconds} s.`}
      </p>
      {details.llmError && (
        <Alert variant="warning">
          <TriangleAlertIcon />
          <AlertTitle>The LLM step failed</AlertTitle>
          <AlertDescription>
            {details.llmError} Only the page&apos;s structured data was used; fill in the remaining fields by hand.
          </AlertDescription>
        </Alert>
      )}
      {details.finalUrl && evidence.run?.url && details.finalUrl !== evidence.run.url && (
        <p className="text-sm text-muted-foreground">
          The page redirected to <ExternalLink href={details.finalUrl} />.
        </p>
      )}
      {details.imageUrl && (
        <p className="text-sm text-muted-foreground">
          Suggested image (not downloaded): <ExternalLink href={details.imageUrl} />
        </p>
      )}
      <ul className="divide-y">
        {evidence.fields.map((item) => (
          <FieldItem key={item.field} item={item} />
        ))}
      </ul>
    </div>
  )
}

function EvidenceCard({ description, children }: { description: string; children: React.ReactNode }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Imported fields</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  )
}

export async function FieldEvidenceSection({ eventId }: { eventId: string }) {
  const result = await api.getEventEvidence(eventId)
  if (!result.ok) {
    return (
      <EvidenceCard description="Evidence from the URL import.">
        <ApiErrorState error={result.error} />
      </EvidenceCard>
    )
  }
  // Events entered by hand have no evidence.
  if (result.data.fields.length === 0) return null
  return (
    <EvidenceCard
      description={`From the URL import of ${formatDateTime(result.data.extracted_at)}. Check each value against its snippet; the import never verifies an event.`}
    >
      <EvidenceDetails evidence={result.data} />
    </EvidenceCard>
  )
}
