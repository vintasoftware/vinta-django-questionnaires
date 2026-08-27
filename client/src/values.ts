/** Reading answer values the way the Python side reads them. */

/** Python's emptiness, not JavaScript's: `[]` and `{}` are empty, `0` is not. */
export function isEmpty(value: unknown): boolean {
  if (value === null || value === undefined || value === "") return true
  if (Array.isArray(value)) return value.length === 0
  if (isPlainObject(value)) return Object.keys(value).length === 0
  return false
}

/** Python's truthiness, used for conditions and predicates. */
export function isTruthy(value: unknown): boolean {
  if (value === null || value === undefined) return false
  if (typeof value === "boolean") return value
  if (typeof value === "number") return value !== 0
  if (typeof value === "string") return value.length > 0
  if (Array.isArray(value)) return value.length > 0
  if (isPlainObject(value)) return Object.keys(value).length > 0
  return true
}

export function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

export function asText(value: unknown): string | null {
  return typeof value === "string" ? value : null
}

export function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null
}

export function asSequence(value: unknown): unknown[] | null {
  return Array.isArray(value) ? value : null
}

export function asFiles(value: unknown): Record<string, unknown>[] | null {
  if (isPlainObject(value)) return [value]
  if (Array.isArray(value) && value.every(isPlainObject))
    return value as Record<string, unknown>[]
  return null
}

/** A stable JSON rendering, matching `json.dumps(..., sort_keys=True)`. */
export function stableStringify(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(",")}]`
  if (isPlainObject(value)) {
    const entries = Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`)
    return `{${entries.join(",")}}`
  }
  return JSON.stringify(value) ?? "null"
}

export function deepEquals(left: unknown, right: unknown): boolean {
  return stableStringify(left) === stableStringify(right)
}

const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/
const TIME_ONLY = /^\d{2}:\d{2}(:\d{2})?(\.\d+)?$/
const HAS_ZONE = /(Z|[+-]\d{2}:?\d{2})$/

export type Temporal = { kind: "moment" | "time"; value: number }

/**
 * Parse an ISO date, datetime or time.
 *
 * A bare date is read as that day's midnight and a naive datetime as UTC, so a
 * date and a datetime compare the way `comparable_temporals` makes them.
 */
export function asTemporal(value: unknown): Temporal | null {
  if (typeof value !== "string") return null
  if (DATE_ONLY.test(value)) return { kind: "moment", value: Date.parse(`${value}T00:00:00Z`) }
  if (TIME_ONLY.test(value)) {
    const [hours, minutes, seconds] = value.split(":")
    return {
      kind: "time",
      value: Number(hours) * 3600 + Number(minutes) * 60 + Number(seconds ?? 0),
    }
  }
  if (value.includes("T")) {
    const parsed = Date.parse(HAS_ZONE.test(value) ? value : `${value}Z`)
    return Number.isNaN(parsed) ? null : { kind: "moment", value: parsed }
  }
  return null
}

export function comparableTemporals(left: unknown, right: unknown): [number, number] | null {
  const first = asTemporal(left)
  const second = asTemporal(right)
  if (!first || !second || first.kind !== second.kind) return null
  return [first.value, second.value]
}
