import { describe, expect, it } from "vitest"

import { parseErrorResponse, unreachableError } from "./errors"

describe("parseErrorResponse", () => {
  it("maps FastAPI field errors to body field names", () => {
    const error = parseErrorResponse(422, {
      detail: [
        { loc: ["body", "official_url"], msg: "Value error, URL scheme must be http or https", type: "value_error" },
        { loc: ["body", "title"], msg: "String should have at least 3 characters", type: "string_too_short" },
      ],
    })
    expect(error.kind).toBe("validation")
    expect(error.fieldErrors).toEqual({
      official_url: "URL scheme must be http or https",
      title: "String should have at least 3 characters",
    })
    expect(error.message).toMatch(/marked fields/)
  })

  it("keeps model-level 422 errors as the message", () => {
    const error = parseErrorResponse(422, {
      detail: [{ loc: ["body"], msg: "Value error, cannot be null: title", type: "value_error" }],
    })
    expect(error.fieldErrors).toEqual({})
    expect(error.message).toBe("Cannot be null: title.")
  })

  it("uses the 409 guard detail verbatim as a sentence", () => {
    const error = parseErrorResponse(409, { detail: "cannot approve: summary is required" })
    expect(error).toMatchObject({ kind: "conflict", status: 409, message: "Cannot approve: summary is required." })
  })

  it("does not double the final period", () => {
    expect(parseErrorResponse(404, { detail: "event not found." }).message).toBe("Event not found.")
  })

  it("explains 401 without echoing anything from the response", () => {
    const error = parseErrorResponse(401, { detail: "invalid or missing bearer token" })
    expect(error.kind).toBe("unauthorized")
    expect(error.message).toContain("ADMIN_API_TOKEN")
  })

  it("maps 503 and unknown statuses", () => {
    expect(parseErrorResponse(503, { detail: "database unavailable" }).kind).toBe("unavailable")
    expect(parseErrorResponse(500, null)).toMatchObject({ kind: "server", message: "The API failed with HTTP 500." })
  })

  it("names the URL when the API is down", () => {
    expect(unreachableError("http://127.0.0.1:8000").message).toMatch(/^API not reachable at http:\/\/127\.0\.0\.1:8000\./)
  })
})
