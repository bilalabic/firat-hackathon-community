import { describe, expect, it } from "vitest"

import { DEFAULT_ALLOWED_HOSTS, isAllowedHost, isAllowedRequest, parseAllowedHosts } from "./host-check"

const allowed = DEFAULT_ALLOWED_HOSTS
const request = (host: string | null, origin: string | null = null, forwardedHost: string | null = null) =>
  isAllowedRequest({ host, origin, forwardedHost }, allowed)

describe("host allow-list", () => {
  it("accepts loopback names on any port by default", () => {
    expect(isAllowedHost("127.0.0.1:3001", allowed)).toBe(true)
    expect(isAllowedHost("localhost:3300", allowed)).toBe(true)
    expect(isAllowedHost("LOCALHOST", allowed)).toBe(true)
  })

  it("rejects foreign, look-alike and malformed hosts", () => {
    expect(isAllowedHost("attacker.example:3400", allowed)).toBe(false)
    expect(isAllowedHost("127.0.0.1.attacker.example", allowed)).toBe(false)
    expect(isAllowedHost("localhost.evil:3001", allowed)).toBe(false)
    expect(isAllowedHost("127.0.0.1:3001@evil", allowed)).toBe(false)
    expect(isAllowedHost("", allowed)).toBe(false)
    expect(isAllowedHost(null, allowed)).toBe(false)
  })

  it("supports exact host:port entries from ADMIN_ALLOWED_HOSTS", () => {
    const list = parseAllowedHosts(" 127.0.0.1:3001 , [::1]:3001 ")
    expect(isAllowedHost("127.0.0.1:3001", list)).toBe(true)
    expect(isAllowedHost("127.0.0.1:3002", list)).toBe(false)
    expect(isAllowedHost("[::1]:3001", list)).toBe(true)
    expect(isAllowedHost("localhost:3001", list)).toBe(false)
    expect(parseAllowedHosts("")).toEqual(DEFAULT_ALLOWED_HOSTS)
    expect(parseAllowedHosts(undefined)).toEqual(DEFAULT_ALLOWED_HOSTS)
  })

  it("checks Origin and X-Forwarded-Host as well as Host", () => {
    expect(request("127.0.0.1:3001")).toBe(true)
    expect(request("127.0.0.1:3001", "http://127.0.0.1:3001")).toBe(true)
    expect(request("evil.example:3400", "http://evil.example:3400")).toBe(false)
    expect(request("127.0.0.1:3001", "http://evil.example:3400")).toBe(false)
    expect(request("127.0.0.1:3001", "null")).toBe(false)
    expect(request("127.0.0.1:3001", null, "evil.example")).toBe(false)
    expect(request("127.0.0.1:3001", null, "127.0.0.1:3001")).toBe(true)
  })
})
