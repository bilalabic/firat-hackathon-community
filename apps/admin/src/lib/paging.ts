// URL search-param helpers for list pages. Pure.

export type SearchParams = Record<string, string | string[] | undefined>

export const PAGE_SIZE = 25

export function firstParam(params: SearchParams, key: string): string | undefined {
  const value = params[key]
  return Array.isArray(value) ? value[0] : value
}

/** Page number from `?page=` (1-based); invalid values fall back to 1. */
export function parsePage(params: SearchParams): number {
  const page = Number(firstParam(params, "page"))
  return Number.isInteger(page) && page >= 1 ? page : 1
}

export function pageOffset(page: number, limit = PAGE_SIZE): number {
  return (page - 1) * limit
}

/** `path?a=1&b=2`, skipping empty values. */
export function hrefWith(path: string, params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value))
  }
  const text = search.toString()
  return text ? `${path}?${text}` : path
}
