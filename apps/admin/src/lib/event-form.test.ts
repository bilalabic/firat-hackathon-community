import { describe, expect, it } from "vitest"

import type { Event } from "@/lib/api/types"

import { EMPTY_EVENT_VALUES, buildEventPayload, changedFields, eventToFormValues } from "./event-form"

const event = {
  id: "00000000-0000-4000-8000-000000000001",
  slug: "zz-test",
  title: "ZZ Test",
  organizer: null,
  summary: "Short summary",
  description: null,
  categories: ["ai", "health"],
  technologies: [],
  format: "online",
  city: null,
  country: "TR",
  venue: null,
  start_date: "2026-11-01",
  end_date: null,
  application_deadline: null,
  timezone: "Europe/Istanbul",
  eligibility: null,
  team_min: 2,
  team_max: null,
  prize_pool: "5000.00",
  currency: "TRY",
  is_free: true,
  official_url: "https://example.com/",
  official_url_normalized: "example.com",
  application_url: null,
  poster_url: null,
  banner_url: null,
  organizer_logo_url: null,
  status: "draft",
  verification_status: "unverified",
  duplicate_of: null,
  internal_notes: null,
  created_at: "2026-10-01T00:00:00Z",
  updated_at: "2026-10-01T00:00:00Z",
  discovered_at: null,
  verified_at: null,
  published_at: null,
  archived_at: null,
  allowed_actions: ["submit"],
} satisfies Event

describe("buildEventPayload", () => {
  it("converts form strings to JSON types and empty optionals to null", () => {
    const { payload, fieldErrors } = buildEventPayload({
      ...EMPTY_EVENT_VALUES,
      title: "  ZZ Test ",
      official_url: "https://example.com/",
      categories: "AI, health, ai,",
      team_min: "2",
      is_free: "false",
      country: "tr",
      prize_pool: "5000",
    })
    expect(fieldErrors).toEqual({})
    expect(payload).toMatchObject({
      title: "ZZ Test",
      organizer: null,
      categories: ["ai", "health"],
      technologies: [],
      team_min: 2,
      team_max: null,
      is_free: false,
      country: "TR",
      prize_pool: "5000",
      format: null,
      start_date: null,
      timezone: "Europe/Istanbul",
      verification_status: "unverified",
    })
  })

  it("sends an empty required field as text so the API reports it per field", () => {
    expect(buildEventPayload({ ...EMPTY_EVENT_VALUES }).payload.title).toBe("")
  })

  it("rejects values that cannot be converted", () => {
    const { fieldErrors } = buildEventPayload({ ...EMPTY_EVENT_VALUES, team_max: "two", prize_pool: "1,5" })
    expect(Object.keys(fieldErrors).sort()).toEqual(["prize_pool", "team_max"])
  })
})

describe("changedFields", () => {
  it("is empty when the form is saved unchanged", () => {
    const { payload } = buildEventPayload(eventToFormValues(event))
    expect(changedFields(payload, event)).toEqual({})
  })

  it("treats 5000 and 5000.00 as the same prize pool", () => {
    const { payload } = buildEventPayload({ ...eventToFormValues(event), prize_pool: "5000" })
    expect(changedFields(payload, event)).toEqual({})
  })

  it("returns only edited fields, with null for cleared ones", () => {
    const { payload } = buildEventPayload({ ...eventToFormValues(event), summary: "", city: "Elazığ" })
    expect(changedFields(payload, event)).toEqual({ summary: null, city: "Elazığ" })
  })
})
