import { beforeEach, describe, expect, it, vi } from "vitest"

import { parseErrorResponse, timeoutError, unreachableError, type ApiError } from "@/lib/api/errors"
import { MAY_HAVE_APPLIED } from "@/lib/channel"

import { deleteChannelPost, resolveChannelPost, sendChannelPost, updateChannelPost } from "./channel"

// vi.mock is hoisted above the imports; the mocks it uses must be too.
const { api, refresh } = vi.hoisted(() => ({
  refresh: vi.fn(),
  api: {
    sendChannelPost: vi.fn(),
    updateChannelPost: vi.fn(),
    deleteChannelPost: vi.fn(),
    resolveChannelPost: vi.fn(),
  },
}))
vi.mock("next/cache", () => ({ refresh }))
// The real client is server-only (bearer token); the actions only need these calls.
vi.mock("@/lib/api/client", () => ({ api }))

const EVENT = "22222222-2222-4222-8222-222222222222"
const POST = "11111111-1111-4111-8111-111111111111"
const HASH = "a".repeat(64)

const failWith = (error: ApiError) => ({ ok: false as const, error })

const ERRORS: [string, ApiError][] = [
  ["conflict", parseErrorResponse(409, { detail: "the event changed since the preview" })],
  ["upstream", parseErrorResponse(502, { detail: "Telegram refused the request." })],
  ["validation", parseErrorResponse(422, { detail: "invalid" })],
  ["not_found", parseErrorResponse(404, { detail: "post not found" })],
  ["timeout", timeoutError(100)],
  ["unreachable", unreachableError("http://127.0.0.1:8000")],
]

beforeEach(() => {
  refresh.mockClear()
  Object.values(api).forEach((fn) => fn.mockReset())
})

describe("channel Server Actions", () => {
  it.each(ERRORS)("re-render the page and return the kind on %s", async (kind, error) => {
    api.deleteChannelPost.mockResolvedValue(failWith(error))
    const result = await deleteChannelPost({ eventId: EVENT, publicationId: POST })
    expect(result).toEqual({ ok: false, kind, message: error.message })
    expect(refresh).toHaveBeenCalledTimes(1)
  })

  it.each(["timeout", "unreachable"] as const)(
    "warn that a send or update may have been applied after %s",
    async (kind) => {
      const error = kind === "timeout" ? timeoutError(100) : unreachableError("http://127.0.0.1:8000")
      api.sendChannelPost.mockResolvedValue(failWith(error))
      api.updateChannelPost.mockResolvedValue(failWith(error))
      for (const action of [sendChannelPost, updateChannelPost]) {
        const result = await action({ eventId: EVENT, contentHash: HASH })
        expect(result).toEqual({ ok: false, kind, message: `${error.message} ${MAY_HAVE_APPLIED}` })
      }
      expect(refresh).toHaveBeenCalledTimes(2)
    }
  )

  it("does not add the warning to a clear refusal or to resolve", async () => {
    const conflict = parseErrorResponse(409, { detail: "the event is already posted" })
    api.sendChannelPost.mockResolvedValue(failWith(conflict))
    expect(await sendChannelPost({ eventId: EVENT, contentHash: HASH })).toEqual({
      ok: false,
      kind: "conflict",
      message: "The event is already posted.",
    })
    api.resolveChannelPost.mockResolvedValue(failWith(timeoutError(15)))
    const resolved = await resolveChannelPost({ eventId: EVENT, publicationId: POST })
    expect(resolved.message).not.toContain(MAY_HAVE_APPLIED)
  })

  it("returns the API message on success and re-renders", async () => {
    api.resolveChannelPost.mockResolvedValue({ ok: true, data: { message: "Marked as not posted." } })
    expect(await resolveChannelPost({ eventId: EVENT, publicationId: POST })).toEqual({
      ok: true,
      message: "Marked as not posted.",
    })
    expect(api.resolveChannelPost).toHaveBeenCalledWith(EVENT, POST, { outcome: "not_in_channel" })
    expect(refresh).toHaveBeenCalledTimes(1)
  })

  it("rejects invalid input without calling the API", async () => {
    expect(await sendChannelPost({ eventId: "x", contentHash: HASH })).toMatchObject({ ok: false, kind: "invalid" })
    expect(await updateChannelPost({ eventId: EVENT, contentHash: "nothex" })).toMatchObject({ ok: false, kind: "invalid" })
    expect(api.sendChannelPost).not.toHaveBeenCalled()
    expect(refresh).not.toHaveBeenCalled()
  })
})
