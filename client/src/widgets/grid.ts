/**
 * The responsive grid, resolved the way the server's layout model describes it.
 *
 * A questionnaire declares window size ranges. Every layer -- the version, a
 * page, a section -- may say how many columns its grid has in each range, and
 * inherits from its parent where it says nothing. Questions work the other way
 * round: each declares the *minimum* number of columns it needs, and is laid
 * out at that width or the whole row, whichever is narrower.
 *
 * The server resolves all of that before it sends a plan, so a renderer only
 * has to pack questions into rows. The editor has no resolved plan to read --
 * it holds a document being typed into -- so the same functions serve both:
 * `columnsFor` walks the inheritance, `packRows` does the packing.
 */

import type { PagePlan, QuestionPlan, QuestionnairePlan, SectionPlan } from "../plan.js"
import type { WindowSizeRangePlan } from "../plan.js"

/** The column count assumed when no layer defines one, as the server has it. */
export const DEFAULT_COLUMN_COUNT = 12

/** The range a viewport *width* falls in, or the first one as a fallback. */
export function rangeForWidth(
  ranges: readonly WindowSizeRangePlan[],
  width: number,
): WindowSizeRangePlan | undefined {
  const match = ranges.find(
    (range) => range.minWidth <= width && (range.maxWidth === null || width <= range.maxWidth),
  )
  return match ?? ranges[0]
}

/** The narrowest a preview is worth rendering at. */
const MIN_PREVIEW_WIDTH = 320

/**
 * How far above its floor an unbounded range renders: a quarter again.
 *
 * A top range has no maximum to take a midpoint of, and its minimum is the
 * boundary it shares with the range below -- the one width at which it looks
 * exactly like its neighbour. So it renders clear of that floor instead.
 */
const UNBOUNDED_HEADROOM = 1.25

/**
 * A width worth rendering *range* at.
 *
 * The midpoint of a bounded range, and clear of the floor of an unbounded one.
 * It used to be each range's widest point, which is the single worst choice
 * available: the widest tablet is one pixel off the narrowest desktop, so two
 * adjacent ranges previewed identically, and a "phone" range of 0-767 rendered
 * at 767 -- a width no phone has ever had.
 *
 * The midpoint is representative rather than exhaustive. It is not where a
 * layout breaks; that is at the edges, and the way to see an edge is to say so
 * -- give the preview a `rangeKey` and a `width` of your own.
 */
export function widthOf(range: WindowSizeRangePlan | undefined, fallback = 1280): number {
  if (!range) return fallback
  const width =
    range.maxWidth === null
      ? Math.round(range.minWidth * UNBOUNDED_HEADROOM) || fallback
      : Math.round((range.minWidth + range.maxWidth) / 2)
  return Math.max(MIN_PREVIEW_WIDTH, width)
}

/**
 * The column count for *rangeKey*, taking the first layer that declares one.
 *
 * The layers are given outermost first, so a section's own count wins over the
 * page's, which wins over the questionnaire's.
 */
export function columnsFor(
  layers: readonly (Record<string, number> | undefined)[],
  rangeKey: string,
  fallback = DEFAULT_COLUMN_COUNT,
): number {
  for (let index = layers.length - 1; index >= 0; index -= 1) {
    const declared = layers[index]?.[rangeKey]
    if (typeof declared === "number" && declared > 0) return declared
  }
  return fallback
}

/** How wide *question* wants to be, never wider than the grid it sits in. */
export function spanOf(
  question: Pick<QuestionPlan, "minimumColumns">,
  rangeKey: string,
  columns: number,
): number {
  const wanted = question.minimumColumns[rangeKey] ?? DEFAULT_COLUMN_COUNT
  return Math.max(1, Math.min(columns, wanted))
}

/** One row of a laid-out grid: the questions in it, and how wide each is. */
export interface GridRow<Question> {
  items: { question: Question; span: number }[]
}

/**
 * Pack *questions* into rows of *columns*, honouring what each one asks for.
 *
 * A question that must be first in its row opens a new one, and one that must
 * be last closes the row it lands in -- which is what those two flags are for,
 * and what nothing on the client did with them until now.
 */
export function packRows<
  Question extends Pick<
    QuestionPlan,
    "minimumColumns" | "requiresBeingFirstInARow" | "requiresBeingLastInARow"
  >,
>(questions: readonly Question[], rangeKey: string, columns: number): GridRow<Question>[] {
  const rows: GridRow<Question>[] = []
  let current: GridRow<Question> | null = null
  let used = 0

  for (const question of questions) {
    const span = spanOf(question, rangeKey, columns)
    const startsFresh =
      current === null || question.requiresBeingFirstInARow || used + span > columns
    if (startsFresh) {
      current = { items: [] }
      rows.push(current)
      used = 0
    }
    // `current` is assigned on every path that could have left it null.
    ;(current as GridRow<Question>).items.push({ question, span })
    used += span
    if (question.requiresBeingLastInARow || used >= columns) {
      current = null
      used = 0
    }
  }

  return rows
}

/** The column counts a page resolves to, layer by layer. */
export function pageColumns(plan: QuestionnairePlan, page: PagePlan, rangeKey: string): number {
  return columnsFor([plan.columns, page.columns], rangeKey)
}

/** The column counts a section resolves to, layer by layer. */
export function sectionColumns(
  plan: QuestionnairePlan,
  page: PagePlan,
  section: SectionPlan,
  rangeKey: string,
): number {
  return columnsFor([plan.columns, page.columns, section.columns], rangeKey)
}
