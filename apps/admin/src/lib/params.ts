import { z } from "zod"

const uuid = z.uuid()

/** Route ids are UUIDs; anything else is a 404 without calling the API. */
export function isUuid(value: string): boolean {
  return uuid.safeParse(value).success
}
