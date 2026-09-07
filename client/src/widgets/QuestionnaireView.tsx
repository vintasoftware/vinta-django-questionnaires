/**
 * A questionnaire, rendered from the plan the server sends.
 *
 * The plan is already resolved -- widgets picked, columns inherited, checks
 * phrased -- so this does two things the plan leaves to the client: it decides
 * which window size range is in force, and it packs each section's questions
 * into rows of that range's grid. Everything inside a question is the widget's
 * business, and which widget that is comes from the registry.
 *
 * It renders no chrome it does not need: no submit button, no page navigation,
 * no progress. A questionnaire is a long-lived thing a host wraps in its own
 * flow, and the parts that differ between flows are exactly the ones that would
 * be hardest to override. What is here is the part that is the same everywhere.
 */

import { useId } from "react"

// Side effect on purpose, and here rather than only in the entry point: this is
// the module that looks a widget up, so importing it has to be enough to have
// something to find. Reaching it another way -- the editor's preview does --
// would otherwise render a form of "nothing renders this".
import "./defaults.js"

import type { PagePlan, QuestionPlan, QuestionnairePlan, SectionPlan } from "../plan.js"
import { useStrings, type WithStrings } from "../editor/strings.js"
import { packRows, pageColumns, rangeForWidth, sectionColumns } from "./grid.js"
import { resolveWidget, type WidgetOption } from "./registry.js"

/** The answers, keyed the way the server keys them: by question key. */
export type Answers = Record<string, unknown>

/** What failed, per question key, already phrased. */
export type AnswerErrors = Record<string, readonly string[]>

/** Options for the questions whose value set the client resolves itself. */
export type ResolvedOptions = Record<
  string,
  { options: readonly WidgetOption[]; isPending?: boolean } | undefined
>

export interface QuestionnaireViewProps extends WithStrings {
  plan: QuestionnairePlan
  answers: Answers
  onChange: (key: string, value: unknown) => void
  errors?: AnswerErrors
  /**
   * The viewport width to lay out against. A host that already knows its own
   * breakpoints passes `rangeKey` instead; the editor's preview passes a width
   * because picking a width is the whole point of it.
   */
  width?: number
  rangeKey?: string
  /** Show the grid the questions are packed into. Off outside the editor. */
  showsGrid?: boolean
  disabled?: boolean
  readOnly?: boolean
  options?: ResolvedOptions
  className?: string
}

export function QuestionnaireView(props: QuestionnaireViewProps) {
  const t = useStrings(props.strings)
  const range =
    props.plan.windowSizeRanges.find((entry) => entry.key === props.rangeKey) ??
    rangeForWidth(props.plan.windowSizeRanges, props.width ?? 1024)
  // No ranges declared is not an error: it is a questionnaire that has not been
  // laid out yet, and one column per row is the honest way to show that.
  const rangeKey = range?.key ?? ""

  return (
    <div className={`vqf ${props.className ?? ""}`.trim()}>
      <header className="vqf__header">
        <h1 className="vqf__title">{props.plan.title}</h1>
        {props.plan.description ? (
          <p className="vqf__description">{props.plan.description}</p>
        ) : null}
      </header>
      {props.plan.pages.map((page) => (
        <PageView key={page.key} {...props} page={page} rangeKey={rangeKey} t={t} />
      ))}
      {props.plan.pages.length ? null : <p className="vqf-empty">{t("view.noPages")}</p>}
    </div>
  )
}

type Shared = QuestionnaireViewProps & { rangeKey: string; t: ReturnType<typeof useStrings> }

function PageView({ page, ...props }: Shared & { page: PagePlan }) {
  const columns = pageColumns(props.plan, page, props.rangeKey)
  return (
    <section className="vqf-page" aria-labelledby={`vqf-page-${page.key}`}>
      <header className="vqf-page__header">
        <h2 className="vqf-page__title" id={`vqf-page-${page.key}`}>
          {page.title}
        </h2>
        <span className="vqf-page__meta">
          {page.isSkippable ? (
            <span className="vqf-tag">{props.t("view.skippable")}</span>
          ) : null}
          {page.condition ? (
            <span className="vqf-tag" title={page.condition}>
              {props.t("view.conditional")}
            </span>
          ) : null}
        </span>
      </header>
      {page.description ? <p className="vqf-page__description">{page.description}</p> : null}
      {page.sections.map((section) => (
        <SectionView
          key={section.key}
          {...props}
          page={page}
          section={section}
          inherited={columns}
        />
      ))}
      {page.conclusion ? <p className="vqf-page__conclusion">{page.conclusion}</p> : null}
    </section>
  )
}

function SectionView({
  page,
  section,
  ...props
}: Shared & { page: PagePlan; section: SectionPlan; inherited: number }) {
  const columns = sectionColumns(props.plan, page, section, props.rangeKey)
  const rows = packRows(section.questions, props.rangeKey, columns)

  return (
    // `open` rather than a state of its own: a section that starts collapsed
    // is a default, not a lock, and `details` already knows how to be one.
    <details className="vqf-section" open={section.defaultState !== "closed"}>
      <summary className="vqf-section__summary">
        <span className="vqf-section__title">{section.title}</span>
        {section.condition ? (
          <span className="vqf-tag" title={section.condition}>
            {props.t("view.conditional")}
          </span>
        ) : null}
      </summary>
      {section.description ? (
        <p className="vqf-section__description">{section.description}</p>
      ) : null}
      <div
        className={`vqf-grid${props.showsGrid ? " vqf-grid--shown" : ""}`}
        style={{ ["--vqf-columns" as string]: columns }}
        data-columns={columns}
      >
        {rows.map((row, index) =>
          row.items.map(({ question, span }) => (
            <div
              className="vqf-cell"
              key={question.key}
              style={{ ["--vqf-span" as string]: span }}
              data-span={span}
              data-row={index}
            >
              <QuestionView {...props} question={question} span={span} columns={columns} />
            </div>
          )),
        )}
        {section.questions.length ? null : (
          <p className="vqf-empty">{props.t("view.noQuestions")}</p>
        )}
      </div>
      {section.conclusion ? (
        <p className="vqf-section__conclusion">{section.conclusion}</p>
      ) : null}
    </details>
  )
}

export interface QuestionViewProps extends Omit<Shared, "page" | "section"> {
  question: QuestionPlan
  span?: number
  columns?: number
}

export function QuestionView({ question, ...props }: QuestionViewProps) {
  const generated = useId()
  const id = `vqf-${question.key}-${generated}`
  const Widget = resolveWidget(question)
  const errors = props.errors?.[question.key] ?? []
  const resolved = props.options?.[question.key]
  const isRequired = question.checks.some((check) => check.validator === "required")
  const describedBy = [
    question.description ? `${id}-description` : null,
    errors.length ? `${id}-errors` : null,
  ]
    .filter(Boolean)
    .join(" ")

  return (
    <div className={`vqf-question${errors.length ? " vqf-question--invalid" : ""}`}>
      <label className="vqf-question__label" id={`${id}-label`} htmlFor={id}>
        {question.title}
        {isRequired ? (
          <span className="vqf-required" title={props.t("view.required")}>
            *
          </span>
        ) : null}
      </label>
      {question.description ? (
        <p className="vqf-question__description" id={`${id}-description`}>
          {question.description}
        </p>
      ) : null}
      <div aria-describedby={describedBy || undefined}>
        {Widget ? (
          <Widget
            question={question}
            id={id}
            value={props.answers[question.key]}
            errors={errors}
            disabled={props.disabled}
            readOnly={props.readOnly}
            options={resolved?.options}
            optionsPending={resolved?.isPending}
            t={props.t}
            onChange={(value) => props.onChange(question.key, value)}
          />
        ) : (
          // Nothing renders this. Said out loud rather than silently skipped:
          // a question the respondent cannot answer is worse than an ugly one.
          <p className="vqf-unrendered">
            {props.t("view.noWidget", { widget: question.widget ?? question.type })}
          </p>
        )}
      </div>
      {errors.length ? (
        <ul className="vqf-question__errors" id={`${id}-errors`}>
          {errors.map((message, index) => (
            <li key={index}>{message}</li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}
