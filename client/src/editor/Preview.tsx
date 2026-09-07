/**
 * What the respondent will see, beside what the author is typing.
 *
 * The pane's job is not decoration -- it is the only place the responsive grid
 * is visible at all. Column counts and minimum widths are numbers stored per
 * breakpoint, and no amount of number fields makes it obvious that a question
 * set to six columns takes half a row on a tablet and a whole one on a phone.
 * So the preview is built around the breakpoints: pick one, and the form is
 * rendered at that range's width, on that range's grid, with the guides on.
 *
 * It renders from `planFromDefinition` rather than from a fetched plan, so it
 * keeps up with the keystroke rather than the save. What that cannot resolve --
 * a value set's options, a nested questionnaire's pages -- is said plainly at
 * the foot of the pane rather than faked.
 */

import { useEffect, useMemo, useRef, useState, type RefObject } from "react"

import type { EditorCatalog, QuestionnaireDefinition } from "../definition.js"
import { planFromDefinition } from "../preview.js"
import type { PagePlan, QuestionnairePlan, SectionPlan } from "../plan.js"
import { QuestionnaireView } from "../widgets/QuestionnaireView.js"
import type { Answers } from "../widgets/QuestionnaireView.js"
import { widthOf } from "../widgets/grid.js"
import type { Selection } from "../editorState.js"
import { describeRange } from "./ColumnPicker.js"
import { useStrings, type WithStrings } from "./strings.js"

/** Below this, the type size is shrunk enough to be worth a warning. */
const NOTICEABLY_SCALED = 0.9

export interface PreviewProps extends WithStrings {
  document: QuestionnaireDefinition
  catalog: EditorCatalog | null
  /** What the outline has selected, so the preview can narrow to it. */
  selection: Selection
  /** Whether the pane has the editor's whole width. */
  isWide?: boolean
  onWide?: (wide: boolean) => void
}

export function Preview({
  document,
  catalog,
  selection,
  strings,
  isWide,
  onWide,
}: PreviewProps) {
  const t = useStrings(strings)
  const [rangeKey, setRangeKey] = useState<string | null>(null)
  const [showsGrid, setShowsGrid] = useState(true)
  const [followsSelection, setFollowsSelection] = useState(true)
  // Held here rather than lifted: what someone types into a preview is not part
  // of the questionnaire, and throwing it away when the pane closes is right.
  const [answers, setAnswers] = useState<Answers>({})

  const stage = useRef<HTMLDivElement>(null)
  const sheet = useRef<HTMLDivElement>(null)
  const [available, setAvailable] = useState(0)
  const [sheetHeight, setSheetHeight] = useState(0)

  const plan = useMemo(() => planFromDefinition(document, catalog), [document, catalog])
  const ranges = plan.windowSizeRanges
  const range = ranges.find((entry) => entry.key === rangeKey) ?? ranges[0]
  const shown = useMemo(
    () => (followsSelection ? narrowTo(plan, selection) : plan),
    [plan, selection, followsSelection],
  )
  const width = widthOf(range)
  // Never scaled up: a phone preview blown up to fill a wide pane would be a
  // lie about how big everything on it is.
  const scale = available && available < width ? available / width : 1

  return (
    <aside className="vqe-preview" aria-label={t("preview.heading")}>
      <Measure stage={stage} sheet={sheet} onStage={setAvailable} onSheet={setSheetHeight} />
      <div className="vqe-preview__bar">
        {ranges.length ? (
          <div className="vqe-preview__ranges" role="group" aria-label={t("preview.range")}>
            {ranges.map((entry) => (
              <button
                type="button"
                key={entry.key}
                className={`vqe-preview__range${entry.key === range?.key ? " is-selected" : ""}`}
                aria-pressed={entry.key === range?.key}
                onClick={() => setRangeKey(entry.key)}
              >
                <span className="vqe-preview__range-name">{entry.label || entry.key}</span>
                <span className="vqe-preview__range-width">{describeRange(entry)}</span>
              </button>
            ))}
          </div>
        ) : (
          <p className="vqe-form__hint">{t("preview.noRanges")}</p>
        )}
        <div className="vqe-preview__toggles">
          <label className="vqe-preview__toggle">
            <input
              type="checkbox"
              checked={showsGrid}
              onChange={(event) => setShowsGrid(event.target.checked)}
            />
            {t("preview.grid")}
          </label>
          <label className="vqe-preview__toggle">
            <input
              type="checkbox"
              checked={followsSelection}
              onChange={(event) => setFollowsSelection(event.target.checked)}
            />
            {t("preview.scope.selection")}
          </label>

          {/* The width being rendered at, which is not the range's own -- a
              range is a span and this is one point in it. Saying the number
              is what keeps that from being a mystery. */}
          <span className="vqe-preview__width">{t("preview.renderedAt", { width })}</span>

          {/* Said out loud, because a scaled preview is a preview with a
              caveat: at 46% the layout is honest and the type size is not, and
              an author deserves to know which of the two they are looking at
              before they judge anything by it. */}
          {/* Flagged only once the shrink is enough to mislead. A preview at
              99% is scaled and worth saying so; it is not worth a warning. */}
          <span
            className={`vqe-preview__scale${scale < NOTICEABLY_SCALED ? " is-scaled" : ""}`}
            title={t(scale < 1 ? "preview.scaledHint" : "preview.actualHint")}
          >
            {scale < 1
              ? t("preview.scaled", { percent: Math.round(scale * 100) })
              : t("preview.actual")}
          </span>

          {onWide ? (
            <button
              type="button"
              className="vqe-preview__widen"
              aria-pressed={!!isWide}
              onClick={() => onWide(!isWide)}
            >
              {t(isWide ? "preview.narrow" : "preview.widen")}
            </button>
          ) : null}
        </div>
      </div>

      {/* The stage is the ruler and the sheet is what is measured. The sheet is
          the range's real width in CSS pixels -- not the pane's -- and is scaled
          down to fit when the pane is narrower. That distinction is the whole
          pane: a form told it is 1024px wide lays out in twelve columns even
          when there are only 380 real pixels to show it in, which is exactly
          the question an author opens the preview to answer. Scaled with a
          transform rather than a zoom, because a transform is applied after
          layout, so the questionnaire's own container queries still see the
          width it was told rather than the width it ended up drawn at. */}
      <div className="vqe-preview__stage" ref={stage}>
        <div
          className="vqe-preview__frame"
          style={{ height: sheetHeight ? `${sheetHeight * scale}px` : undefined }}
        >
          <div
            className="vqe-preview__sheet"
            ref={sheet}
            style={{ width: `${width}px`, transform: `scale(${scale})` }}
          >
            <QuestionnaireView
              plan={shown}
              answers={answers}
              strings={strings}
              showsGrid={showsGrid}
              rangeKey={range?.key}
              width={width}
              onChange={(key, value) => setAnswers((current) => ({ ...current, [key]: value }))}
            />
          </div>
        </div>
      </div>

      <p className="vqe-preview__footnote">{t("preview.approximate")}</p>
    </aside>
  )
}

/**
 * Watches the stage and the sheet, and reports their sizes.
 *
 * Two numbers are wanted and neither is knowable from props: how much room
 * there is to scale into, and how tall the sheet is, so the space it takes up
 * after scaling can be reserved -- a transform does not change layout, so
 * without that the pane would scroll as though nothing had been scaled.
 */
function Measure({
  stage,
  sheet,
  onStage,
  onSheet,
}: {
  stage: RefObject<HTMLDivElement | null>
  sheet: RefObject<HTMLDivElement | null>
  onStage: (width: number) => void
  onSheet: (height: number) => void
}) {
  useEffect(() => {
    const stageElement = stage.current
    const sheetElement = sheet.current
    if (!stageElement || !sheetElement) return
    // Guarded, because the editor is also rendered where there is no observer
    // to be had: a test environment, or a server-side render.
    if (typeof ResizeObserver === "undefined") {
      onStage(stageElement.clientWidth)
      onSheet(sheetElement.offsetHeight)
      return
    }
    const observer = new ResizeObserver(() => {
      onStage(stageElement.clientWidth)
      onSheet(sheetElement.offsetHeight)
    })
    observer.observe(stageElement)
    observer.observe(sheetElement)
    return () => observer.disconnect()
  }, [stage, sheet, onStage, onSheet])
  return null
}

/**
 * The plan cut down to whatever is selected.
 *
 * Selecting a question and seeing the whole questionnaire is not much of an
 * answer to "what does this look like", and a long one makes it a scroll hunt.
 * The page keeps its shell either way, because a question's width only means
 * something inside the grid its section resolves to.
 */
function narrowTo(plan: QuestionnairePlan, selection: Selection): QuestionnairePlan {
  if (selection.kind === "version") return plan
  const page = plan.pages[selection.page]
  if (!page) return plan
  if (selection.kind === "page") return { ...plan, pages: [page] }

  const section = page.sections[selection.section]
  if (!section) return { ...plan, pages: [page] }
  if (selection.kind === "section") {
    return { ...plan, pages: [withSections(page, [section])] }
  }

  const question = section.questions[selection.question]
  if (!question) return { ...plan, pages: [withSections(page, [section])] }
  return {
    ...plan,
    pages: [withSections(page, [{ ...section, questions: [question] }])],
  }
}

function withSections(page: PagePlan, sections: SectionPlan[]): PagePlan {
  return { ...page, sections }
}
