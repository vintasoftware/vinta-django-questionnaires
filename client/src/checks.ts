/**
 * The check table: one entry per `kind` the server can emit.
 *
 * Each entry is the counterpart of a Python validator's `validate()`, and the
 * conformance corpus is what keeps the pair honest.  Where Zod's own check
 * would disagree with Python at the edges -- email, url, uuid -- the table
 * applies the pattern the server shipped instead of Zod's.
 */

import { search } from "jmespath"

import type { ValidationContext } from "./context.js"
import {
  asFiles,
  asNumber,
  asSequence,
  asText,
  comparableTemporals,
  deepEquals,
  isEmpty,
  isTruthy,
  isPlainObject,
  stableStringify,
} from "./values.js"

export interface CheckRunContext {
  value: unknown
  args: unknown[]
  params: Record<string, unknown>
  chain: ValidationContext
  /** Report the check's own error key, or a different declared one. */
  fail(errorKey?: string, params?: Record<string, unknown>): void
}

export type CheckImplementation = (
  context: CheckRunContext,
) => { data?: Record<string, unknown> } | void

/** Shared with `strings.EMAIL_PATTERN` on the server. */
export const EMAIL_PATTERN =
  /^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$/
/** Shared with `strings.URL_PATTERN`. */
export const URL_PATTERN = /^[A-Za-z][A-Za-z0-9+.-]*:\/\/[^\s/?#]+\S*$/
/** Shared with `strings.UUID_PATTERN`. */
export const UUID_PATTERN =
  /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/

function text(context: CheckRunContext): string | null {
  return asText(context.value)
}

function matches(pattern: RegExp, context: CheckRunContext): void {
  const value = text(context)
  if (value === null) return
  if (!pattern.test(value)) context.fail()
}

export const checks: Record<string, CheckImplementation> = {
  "presence.required": ({ value, fail }) => {
    if (isEmpty(value)) fail()
  },

  "string.min": (context) => {
    const value = text(context)
    if (value === null) return
    if (value.length < Number(context.args[0])) context.fail()
    return { data: { length: value.length } }
  },

  "string.max": (context) => {
    const value = text(context)
    if (value === null) return
    if (value.length > Number(context.args[0])) context.fail()
    return { data: { length: value.length } }
  },

  "string.regex": (context) => {
    const value = text(context)
    if (value === null) return
    const [pattern, ignoreCase] = context.args
    if (!new RegExp(String(pattern), ignoreCase ? "i" : "").test(value)) context.fail()
  },

  "string.email": (context) => matches(EMAIL_PATTERN, context),
  "string.url": (context) => matches(URL_PATTERN, context),
  "string.uuid": (context) => matches(UUID_PATTERN, context),

  "string.startsWith": (context) => {
    const value = text(context)
    if (value === null) return
    if (!value.startsWith(String(context.args[0]))) context.fail()
  },

  "string.endsWith": (context) => {
    const value = text(context)
    if (value === null) return
    if (!value.endsWith(String(context.args[0]))) context.fail()
  },

  "string.includes": (context) => {
    const value = text(context)
    if (value === null) return
    if (!value.includes(String(context.args[0]))) context.fail()
  },

  "number.gte": ({ value, args, fail }) => {
    const number = asNumber(value)
    if (number !== null && number < Number(args[0])) fail()
  },

  "number.gt": ({ value, args, fail }) => {
    const number = asNumber(value)
    if (number !== null && number <= Number(args[0])) fail()
  },

  "number.lte": ({ value, args, fail }) => {
    const number = asNumber(value)
    if (number !== null && number > Number(args[0])) fail()
  },

  "number.lt": ({ value, args, fail }) => {
    const number = asNumber(value)
    if (number !== null && number >= Number(args[0])) fail()
  },

  "number.int": ({ value, fail }) => {
    const number = asNumber(value)
    if (number !== null && !Number.isInteger(number)) fail()
  },

  "number.multipleOf": ({ value, args, fail }) => {
    const number = asNumber(value)
    const step = Number(args[0])
    if (number === null || !step) return
    // Scale both sides to integers so 0.3 % 0.1 does not drift, the way the
    // server's Decimal arithmetic does not drift.
    const decimals = Math.max(decimalPlaces(number), decimalPlaces(step))
    const factor = 10 ** decimals
    if (Math.round(number * factor) % Math.round(step * factor) !== 0) fail()
  },

  "date.min": ({ value, args, fail }) => {
    const pair = comparableTemporals(value, args[0])
    if (pair && pair[0] < pair[1]) fail()
  },

  "date.max": ({ value, args, fail }) => {
    const pair = comparableTemporals(value, args[0])
    if (pair && pair[0] > pair[1]) fail()
  },

  "range.ordered": ({ value, fail }) => {
    if (!isPlainObject(value) || (!("start" in value) && !("end" in value))) {
      return fail("invalid_type")
    }
    const start = value.start
    const end = value.end
    if (start === null || start === undefined || end === null || end === undefined) {
      return fail("incomplete_range")
    }
    const startNumber = asNumber(start)
    const endNumber = asNumber(end)
    if (startNumber !== null && endNumber !== null) {
      if (startNumber > endNumber) fail("range_out_of_order")
      return
    }
    const pair = comparableTemporals(start, end)
    if (!pair) return fail("invalid_type")
    if (pair[0] > pair[1]) fail("range_out_of_order")
  },

  "array.min": ({ value, args, fail }) => {
    const items = asSequence(value)
    if (items === null) return
    if (items.length < Number(args[0])) fail()
    return { data: { count: items.length } }
  },

  "array.max": ({ value, args, fail }) => {
    const items = asSequence(value)
    if (items === null) return
    if (items.length > Number(args[0])) fail()
    return { data: { count: items.length } }
  },

  "array.unique": ({ value, fail }) => {
    const items = asSequence(value)
    if (items === null) return
    const seen = new Set(items.map(stableStringify))
    if (seen.size !== items.length) fail()
  },

  "value.oneOf": ({ value, args, fail }) => {
    const allowed = (asSequence(args[0]) ?? []) as unknown[]
    const candidates = asSequence(value) ?? [value]
    for (const candidate of candidates) {
      if (!allowed.some((option) => deepEquals(option, candidate))) {
        fail(undefined, { value: candidate })
        return
      }
    }
  },

  "file.maxSize": ({ value, args, fail }) => {
    const files = asFiles(value)
    if (files === null) return
    for (const file of files) {
      if (Number(file.size ?? 0) > Number(args[0])) {
        fail(undefined, { name: file.name ?? "" })
        return
      }
    }
  },

  "file.contentType": ({ value, args, fail }) => {
    const patterns = (asSequence(args[0]) ?? []).map(String)
    const files = asFiles(value)
    if (files === null) return
    for (const file of files) {
      const contentType = String(file.content_type ?? "")
      const accepted = patterns.some((pattern) =>
        pattern.endsWith("/*")
          ? contentType.startsWith(pattern.slice(0, -1))
          : contentType === pattern,
      )
      if (!accepted) {
        fail(undefined, { name: file.name ?? "" })
        return
      }
    }
  },

  "logic.jmespath": ({ value, args, chain, fail }) => {
    const document = chain.toDocument(value)
    if (!isTruthy(search(document, String(args[0])))) fail()
  },
}

function decimalPlaces(value: number): number {
  const text = String(value)
  const dot = text.indexOf(".")
  return dot === -1 ? 0 : text.length - dot - 1
}

export function hasCheck(kind: string): boolean {
  return kind in checks
}
