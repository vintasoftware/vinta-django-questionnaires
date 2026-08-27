/**
 * Putting the questionnaire's breakpoints onto the design system's.
 *
 * A questionnaire names its own window size ranges -- mobile, tablet, desktop
 * here, but they are whatever the author wrote -- while the design system's
 * Grid takes `base`/`sm`/`md`/`lg`/`xl`. Each range maps to the widest design
 * system breakpoint that starts no later than it does.
 */

import type { Breakpoint } from "vinta-schedule-design-system/layout"

export interface WindowSizeRange {
  key: string
  label: string
  minWidth: number
  maxWidth: number | null
}

const DESIGN_SYSTEM: { key: Breakpoint; minWidth: number }[] = [
  { key: "base", minWidth: 0 },
  { key: "sm", minWidth: 640 },
  { key: "md", minWidth: 768 },
  { key: "lg", minWidth: 1024 },
  { key: "xl", minWidth: 1280 },
]

export function breakpointFor(range: WindowSizeRange): Breakpoint {
  let match: Breakpoint = "base"
  for (const candidate of DESIGN_SYSTEM) {
    if (candidate.minWidth <= range.minWidth) match = candidate.key
  }
  return match
}

/** Turn a per-range value from the plan into a per-breakpoint one. */
export function responsive<T>(
  byRange: Record<string, T> | undefined,
  ranges: WindowSizeRange[],
): Partial<Record<Breakpoint, T>> {
  const out: Partial<Record<Breakpoint, T>> = {}
  for (const range of ranges) {
    const value = byRange?.[range.key]
    if (value !== undefined) out[breakpointFor(range)] = value
  }
  return out
}
