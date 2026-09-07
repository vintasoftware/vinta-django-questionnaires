/**
 * How wide something is, picked on the grid rather than typed as a number.
 *
 * Column counts are the part of a questionnaire that a number field describes
 * worst. "6" means nothing without knowing the grid is twelve wide and that the
 * page next door inherits it; a strip of twelve cells with six of them filled
 * means it at a glance. So this is the control for both sides of the model:
 * how many columns a layer's grid has, and how many of them a question takes.
 *
 * They are radio inputs under the styling, so arrow keys move through the
 * cells, the label is bound, and a screen reader hears "6 of 12" rather than a
 * row of unlabelled buttons.
 */

import { useId } from "react"

import type { QuestionnaireDefinition, WindowSizeRangeDefinition } from "../definition.js"
import { DEFAULT_COLUMN_COUNT } from "../widgets/grid.js"
import { useStrings } from "./strings.js"
import type { Translate } from "../strings.js"

/** The widest grid the picker will draw. Beyond this a strip stops reading. */
const MAX_COLUMNS = 24

export interface CellStripProps {
  /** How many cells to draw. */
  of: number
  /** How many are filled, or `null` for nothing chosen. */
  value: number | null
  onChange: (value: number | null) => void
  label: string
  /** What the caption says when nothing is chosen. */
  inheritedLabel: string
  disabled?: boolean
}

/**
 * The strip itself: *of* cells, the first *value* of them filled.
 *
 * Clicking the cell that is already the last one filled clears the choice,
 * which is how a layer goes back to inheriting without a second control.
 */
export function CellStrip({
  of,
  value,
  onChange,
  label,
  inheritedLabel,
  disabled,
}: CellStripProps) {
  const t = useStrings()
  const name = useId()
  const cells = Array.from({ length: Math.min(of, MAX_COLUMNS) }, (_, index) => index + 1)

  return (
    <div className="vqe-strip">
      <div
        className="vqe-strip__cells"
        role="radiogroup"
        aria-label={label}
        style={{ ["--vqe-strip-cells" as string]: cells.length }}
      >
        {cells.map((cell) => (
          <label
            className={`vqe-strip__cell${value !== null && cell <= value ? " is-filled" : ""}`}
            key={cell}
            title={t("columns.span", { span: cell, columns: of })}
          >
            <input
              type="radio"
              className="vqe-strip__input"
              name={name}
              disabled={disabled}
              checked={value === cell}
              onChange={() => onChange(cell)}
              // A second click on the chosen cell clears it. `onChange` does
              // not fire for that -- the radio is already checked -- so the
              // click is what has to carry it.
              onClick={() => {
                if (value === cell) onChange(null)
              }}
            />
            <span className="vqe-strip__number">{cell}</span>
          </label>
        ))}
      </div>
      <p className="vqe-strip__caption">
        {value === null ? inheritedLabel : t("columns.span", { span: value, columns: of })}
        {value === null ? null : (
          <button
            type="button"
            className="vqe-strip__clear"
            disabled={disabled}
            onClick={() => onChange(null)}
          >
            {t("columns.clear")}
          </button>
        )}
      </p>
    </div>
  )
}

export interface RangeStripsProps {
  document: QuestionnaireDefinition
  /** The value for each range, keyed by range key. Missing means inherited. */
  values: Record<string, number>
  onChange: (range: string, value: number | null) => void
  /** How many cells to draw for *range* -- the grid this sits in. */
  extentOf: (range: WindowSizeRangeDefinition) => number
  /** What the caption says for *range* when nothing is set. */
  inheritedLabel: (range: WindowSizeRangeDefinition) => string
  label: (range: WindowSizeRangeDefinition) => string
  errors?: Record<string, string[]>
}

/** One strip per window size range, which is how the model stores these. */
export function RangeStrips({
  document,
  values,
  onChange,
  extentOf,
  inheritedLabel,
  label,
  errors,
}: RangeStripsProps) {
  return (
    <div className="vqe-strips">
      {document.windowSizeRanges.map((range) => (
        <div className="vqe-strips__row" key={range.key}>
          <div className="vqe-strips__name">
            <span>{range.label || range.key}</span>
            <span className="vqe-strips__width">{describeRange(range)}</span>
          </div>
          <CellStrip
            of={extentOf(range)}
            value={values[range.key] ?? null}
            onChange={(value) => onChange(range.key, value)}
            label={label(range)}
            inheritedLabel={inheritedLabel(range)}
          />
          {errors?.[range.key]?.length ? (
            <ul className="vqe-errors">
              {errors[range.key]?.map((message, index) => (
                <li key={index}>{message}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ))}
    </div>
  )
}

/** A range as the widths it covers, which is what makes its name mean anything. */
export function describeRange(range: WindowSizeRangeDefinition): string {
  return range.maxWidth === null
    ? `${range.minWidth}px+`
    : `${range.minWidth}–${range.maxWidth}px`
}

export interface NoRangesProps {
  t: Translate
  onAddStandard: () => void
  onAddOne: () => void
}

/**
 * What stands in for the strips when there are no ranges to draw them against.
 *
 * The fields used to disappear entirely here, which is why nobody could find
 * them: a column count is stored against a breakpoint, so with no breakpoints
 * there is nowhere to put one -- and the editor said nothing at all rather than
 * saying that. It now names the prerequisite and offers to satisfy it.
 */
export function NoRanges({ t, onAddStandard, onAddOne }: NoRangesProps) {
  return (
    <div className="vqe-prereq">
      <p className="vqe-prereq__title">{t("columns.noRanges")}</p>
      <p className="vqe-form__hint">{t("columns.noRangesHint")}</p>
      <div className="vqe-prereq__actions">
        <button type="button" className="vqe-button vqe-button--plain" onClick={onAddStandard}>
          {t("columns.addStandard")}
        </button>
        <button type="button" className="vqe-button vqe-button--quiet" onClick={onAddOne}>
          {t("columns.addOne")}
        </button>
      </div>
    </div>
  )
}

/** The breakpoints most projects start from, so nobody has to invent them. */
export const STANDARD_RANGES: WindowSizeRangeDefinition[] = [
  { key: "mobile", label: "Phone", minWidth: 0, maxWidth: 767 },
  { key: "tablet", label: "Tablet", minWidth: 768, maxWidth: 1023 },
  { key: "desktop", label: "Desktop", minWidth: 1024, maxWidth: null },
]

export { DEFAULT_COLUMN_COUNT }
