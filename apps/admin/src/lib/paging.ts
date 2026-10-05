// URL search-param helpers for list pages. Pure.

export type SearchParams = Record<string, string | string[] | undefined>

export const PAGE_SIZE = 25

export function firstParam(params: SearchParams, key: string): string | undefined {
  const value = params[key]
  return Array.isArray(value) ? value[0] : value
}

/** Far beyond any real list; keeps the offset a small integer for the API. */
export const MAX_PAGE = 10_000

/** Page number from `?page=` (1-based); invalid or absurd values fall back to 1. */
export function parsePage(params: SearchParams): number {
  const text = firstParam(params, "page") ?? ""
  const page = /^\d{1,5}$/.test(text) ? Number(text) : NaN
  return page >= 1 && page <= MAX_PAGE ? page : 1
}

/** Last page that has rows (at least 1). */
export function lastPage(total: number, limit = PAGE_SIZE): number {
  return Math.max(1, Math.ceil(total / limit))
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
