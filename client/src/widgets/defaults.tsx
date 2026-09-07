/**
 * A working component for every question type, and for every key the default
 * widget set installs.
 *
 * These exist so that a questionnaire renders the moment it is fetched -- in
 * the editor's preview, in a spike, in a project that has not chosen a design
 * system yet. They are plain elements with `vqf-` class names and no
 * dependencies, the same bargain `fields.tsx` makes for the editor: a host
 * restyles them from its own stylesheet, or replaces any of them outright with
 * `registerWidget`.
 *
 * What they are not is a design system. Nothing here tries to be pretty; what
 * they do carry is the part that is hard to redo and easy to get wrong -- a
 * label bound to its control, errors announced against the field that caused
 * them, the "other" escape hatch storing what the respondent typed rather than
 * a sentinel, and the nested shapes (`item_list`, matrices, sub-questionnaires)
 * whose answer format the server is particular about.
 */

import { useId, type ReactNode } from "react"

import type { ChoicePlan, QuestionPlan } from "../plan.js"
import { isExpandedSubQuestionnaire } from "../plan.js"
import { registerDefaultWidget, resolveWidget, type WidgetProps } from "./registry.js"

// ------------------------------------------------------------------ helpers

function asText(value: unknown): string {
  return value === null || value === undefined ? "" : String(value)
}

function asList(value: unknown): unknown[] {
  return Array.isArray(value) ? value : []
}

function asRange(value: unknown): { start?: unknown; end?: unknown } {
  return value && typeof value === "object" ? (value as { start?: unknown; end?: unknown }) : {}
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {}
}

/** The options to show: a resolved value set's, or the question's own choices. */
function optionsOf(props: WidgetProps): readonly { value: string; label: string }[] {
  if (props.options?.length) return props.options
  return props.question.choices ?? []
}

/** A widget's props, which the server already merged with the widget's defaults. */
function propsOf<Shape extends object>(question: QuestionPlan): Partial<Shape> {
  return (question.widgetProps ?? {}) as Partial<Shape>
}

/**
 * Whether *value* is an answer typed into the "other" box rather than a choice.
 *
 * There is no sentinel: a question that allows an other option stores exactly
 * what was typed, which is why its base type is a string rather than an enum.
 * So "other" is not a value to look for -- it is any answer the choices do not
 * account for.
 */
function isOtherValue(value: unknown, choices: readonly ChoicePlan[]): boolean {
  return (
    typeof value === "string" &&
    value !== "" &&
    !choices.some((choice) => choice.value === value)
  )
}

function otherLabelOf(props: WidgetProps): string {
  const declared =
    props.question.otherLabel || propsOf<{ otherLabel: string }>(props.question).otherLabel
  return declared || props.t("widget.other")
}

/** Whether to mark the control invalid, from whatever was reported against it. */
function invalid({ errors }: { errors: readonly string[] }): true | undefined {
  return errors.length ? true : undefined
}

/** The wrapper a multi-control widget puts its own sub-labels in. */
function Part({
  label,
  htmlFor,
  children,
}: {
  label: string
  htmlFor: string
  children: ReactNode
}) {
  return (
    <div className="vqf-part">
      <label className="vqf-part__label" htmlFor={htmlFor}>
        {label}
      </label>
      {children}
    </div>
  )
}

// -------------------------------------------------------------------- text

function TextWidget(props: WidgetProps) {
  const { placeholder, type, autoComplete } = propsOf<{
    placeholder: string
    type: string
    autoComplete: string
  }>(props.question)
  return (
    <input
      id={props.id}
      className="vqf-input"
      type={type ?? inputTypeFor(props.question.type)}
      placeholder={placeholder}
      autoComplete={autoComplete}
      disabled={props.disabled}
      readOnly={props.readOnly}
      aria-invalid={invalid(props)}
      value={asText(props.value)}
      onChange={(event) => props.onChange(event.target.value)}
    />
  )
}

/** The native input type a scalar question is best served by. */
function inputTypeFor(questionType: string): string {
  switch (questionType) {
    case "url":
      return "url"
    case "time":
      return "time"
    case "date":
      return "date"
    case "date_time":
      return "datetime-local"
    case "month":
      return "month"
    case "number":
    case "year":
    case "time_duration":
      return "number"
    default:
      return "text"
  }
}

function TextAreaWidget(props: WidgetProps) {
  const { rows, placeholder } = propsOf<{ rows: number; placeholder: string }>(props.question)
  return (
    <textarea
      id={props.id}
      className="vqf-input vqf-textarea"
      rows={rows ?? 4}
      placeholder={placeholder}
      disabled={props.disabled}
      readOnly={props.readOnly}
      aria-invalid={invalid(props)}
      value={asText(props.value)}
      onChange={(event) => props.onChange(event.target.value)}
    />
  )
}

function NumberWidget(props: WidgetProps) {
  const { prefix, suffix, step, min, max } = propsOf<{
    prefix: string
    suffix: string
    step: number
    min: number
    max: number
  }>(props.question)
  return (
    <span className="vqf-affixed">
      {prefix ? <span className="vqf-affix">{prefix}</span> : null}
      <input
        id={props.id}
        className="vqf-input"
        type="number"
        step={step}
        min={min}
        max={max}
        disabled={props.disabled}
        readOnly={props.readOnly}
        aria-invalid={invalid(props)}
        value={props.value === null || props.value === undefined ? "" : String(props.value)}
        onChange={(event) =>
          props.onChange(event.target.value === "" ? null : Number(event.target.value))
        }
      />
      {suffix ? <span className="vqf-affix">{suffix}</span> : null}
    </span>
  )
}

// ------------------------------------------------------------------ choices

function RadioGroupWidget(props: WidgetProps) {
  const { orientation } = propsOf<{ orientation: string }>(props.question)
  const choices = optionsOf(props)
  const allowsOther = !!props.question.allowsOther
  const other = isOtherValue(props.value, choices)
  const name = useId()

  return (
    <div
      className={`vqf-options vqf-options--${orientation === "horizontal" ? "row" : "column"}`}
      role="radiogroup"
      aria-labelledby={`${props.id}-label`}
      aria-invalid={invalid(props)}
    >
      {choices.map((choice) => (
        <label
          className="vqf-option"
          key={choice.value}
          htmlFor={`${props.id}-${choice.value}`}
        >
          <input
            id={`${props.id}-${choice.value}`}
            type="radio"
            name={name}
            className="vqf-radio"
            disabled={props.disabled}
            checked={props.value === choice.value}
            onChange={() => props.onChange(choice.value)}
          />
          <span>{choice.label || choice.value}</span>
        </label>
      ))}
      {allowsOther ? (
        <div className="vqf-option vqf-option--other">
          <label className="vqf-option">
            <input
              type="radio"
              name={name}
              className="vqf-radio"
              disabled={props.disabled}
              checked={other}
              // Selecting "other" cannot commit a value -- there is none until
              // something is typed -- so it clears the choice and lets the box
              // below take over.
              onChange={() => props.onChange("")}
            />
            <span id={`${props.id}-other-label`}>{otherLabelOf(props)}</span>
          </label>
          {/* Always here, not revealed by its radio. Typing into it is how
              people answer "something else" -- selecting the radio first is a
              step they should not have to find, and a box that appears only
              once the radio is on is a box nobody can type into to begin with.
              Named by the same words as the radio, because it is the same
              answer: a label of its own would give one control two names. */}
          <input
            className="vqf-input"
            aria-labelledby={`${props.id}-other-label`}
            disabled={props.disabled}
            value={other ? asText(props.value) : ""}
            onChange={(event) => props.onChange(event.target.value)}
          />
        </div>
      ) : null}
    </div>
  )
}

function CheckboxGroupWidget(props: WidgetProps) {
  const { columns } = propsOf<{ columns: number }>(props.question)
  const choices = optionsOf(props)
  const selected = asList(props.value)
  const known = new Set(choices.map((choice) => choice.value))
  const typed = selected.find((entry) => typeof entry === "string" && !known.has(entry))

  const toggle = (value: string, on: boolean) =>
    props.onChange(on ? [...selected, value] : selected.filter((entry) => entry !== value))

  return (
    <div
      className="vqf-options vqf-options--grid"
      style={
        columns && columns > 1 ? { ["--vqf-option-columns" as string]: columns } : undefined
      }
      role="group"
      aria-invalid={invalid(props)}
    >
      {choices.map((choice) => (
        <label
          className="vqf-option"
          key={choice.value}
          htmlFor={`${props.id}-${choice.value}`}
        >
          <input
            id={`${props.id}-${choice.value}`}
            type="checkbox"
            className="vqf-checkbox"
            disabled={props.disabled}
            checked={selected.includes(choice.value)}
            onChange={(event) => toggle(choice.value, event.target.checked)}
          />
          <span>{choice.label || choice.value}</span>
        </label>
      ))}
      {props.question.allowsOther ? (
        <div className="vqf-option vqf-option--other">
          <label className="vqf-option">
            <input
              type="checkbox"
              className="vqf-checkbox"
              disabled={props.disabled}
              checked={typed !== undefined}
              onChange={(event) =>
                props.onChange(
                  event.target.checked
                    ? selected
                    : selected.filter((entry) => typeof entry !== "string" || known.has(entry)),
                )
              }
            />
            <span id={`${props.id}-other-label`}>{otherLabelOf(props)}</span>
          </label>
          <input
            className="vqf-input"
            aria-labelledby={`${props.id}-other-label`}
            disabled={props.disabled}
            value={asText(typed)}
            onChange={(event) => {
              const rest = selected.filter(
                (entry) => typeof entry !== "string" || known.has(entry),
              )
              props.onChange(event.target.value ? [...rest, event.target.value] : rest)
            }}
          />
        </div>
      ) : null}
    </div>
  )
}

function SelectWidget(props: WidgetProps) {
  const { placeholder } = propsOf<{ placeholder: string }>(props.question)
  const choices = optionsOf(props)
  return (
    <select
      id={props.id}
      className="vqf-input vqf-select"
      disabled={props.disabled || props.optionsPending}
      aria-invalid={invalid(props)}
      aria-busy={props.optionsPending || undefined}
      value={asText(props.value)}
      onChange={(event) => props.onChange(event.target.value)}
    >
      <option value="">
        {props.optionsPending ? props.t("widget.loading") : (placeholder ?? "")}
      </option>
      {choices.map((choice) => (
        <option key={choice.value} value={choice.value}>
          {choice.label || choice.value}
        </option>
      ))}
    </select>
  )
}

function MultiSelectWidget(props: WidgetProps) {
  const choices = optionsOf(props)
  const selected = asList(props.value).map(String)
  return (
    <select
      id={props.id}
      className="vqf-input vqf-select vqf-select--multiple"
      multiple
      size={Math.min(8, Math.max(3, choices.length))}
      disabled={props.disabled || props.optionsPending}
      aria-invalid={invalid(props)}
      aria-busy={props.optionsPending || undefined}
      value={selected}
      onChange={(event) =>
        props.onChange([...event.target.selectedOptions].map((option) => option.value))
      }
    >
      {choices.map((choice) => (
        <option key={choice.value} value={choice.value}>
          {choice.label || choice.value}
        </option>
      ))}
    </select>
  )
}

// ------------------------------------------------------------------- ranges

function RangeWidget(props: WidgetProps) {
  const { startLabel, endLabel } = propsOf<{ startLabel: string; endLabel: string }>(
    props.question,
  )
  const range = asRange(props.value)
  const numeric = props.question.type === "number_range"
  const type = numeric
    ? "number"
    : props.question.type === "date_time_range"
      ? "datetime-local"
      : "date"
  const set = (edge: "start" | "end", raw: string) =>
    props.onChange({
      ...range,
      [edge]: raw === "" ? null : numeric ? Number(raw) : raw,
    })

  return (
    <div className="vqf-range">
      <Part label={startLabel || props.t("widget.range.start")} htmlFor={`${props.id}-start`}>
        <input
          id={`${props.id}-start`}
          className="vqf-input"
          type={type}
          disabled={props.disabled}
          readOnly={props.readOnly}
          aria-invalid={invalid(props)}
          value={asText(range.start)}
          onChange={(event) => set("start", event.target.value)}
        />
      </Part>
      <Part label={endLabel || props.t("widget.range.end")} htmlFor={`${props.id}-end`}>
        <input
          id={`${props.id}-end`}
          className="vqf-input"
          type={type}
          disabled={props.disabled}
          readOnly={props.readOnly}
          value={asText(range.end)}
          onChange={(event) => set("end", event.target.value)}
        />
      </Part>
    </div>
  )
}

// -------------------------------------------------------------------- files

/** What the server stores for a file: a reference, not the bytes. */
function fileReference(file: File): Record<string, unknown> {
  return { name: file.name, size: file.size, content_type: file.type }
}

function FileWidget(props: WidgetProps) {
  const { accept } = propsOf<{ accept: string }>(props.question)
  const multiple = props.question.type === "multiple_files"
  const chosen = multiple ? asList(props.value) : props.value ? [props.value] : []

  return (
    <div className="vqf-file">
      <input
        id={props.id}
        className="vqf-input"
        type="file"
        accept={accept}
        multiple={multiple}
        disabled={props.disabled}
        aria-invalid={invalid(props)}
        onChange={(event) => {
          const files = [...(event.target.files ?? [])].map(fileReference)
          props.onChange(multiple ? files : (files[0] ?? null))
        }}
      />
      {chosen.length ? (
        <ul className="vqf-file__list">
          {chosen.map((entry, index) => {
            const file = asRecord(entry)
            return <li key={index}>{asText(file.name)}</li>
          })}
        </ul>
      ) : null}
    </div>
  )
}

// ------------------------------------------------------------------- matrix

function MatrixWidget(props: WidgetProps) {
  const matrix = props.question.matrix ?? { rows: [], columns: [] }
  const answer = asRecord(props.value)
  const selectedIn = (row: string) => asList(answer[row]).map(String)

  const toggle = (row: string, column: string, on: boolean) => {
    const current = selectedIn(row)
    const next = on ? [...current, column] : current.filter((entry) => entry !== column)
    props.onChange({ ...answer, [row]: next })
  }

  return (
    <table className="vqf-matrix" aria-invalid={invalid(props)}>
      <thead>
        <tr>
          <td />
          {matrix.columns.map((column) => (
            <th key={column.value} scope="col">
              {column.label || column.value}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {matrix.rows.map((row) => (
          <tr key={row.value}>
            <th scope="row">{row.label || row.value}</th>
            {matrix.columns.map((column) => (
              <td key={column.value}>
                <input
                  type="checkbox"
                  className="vqf-checkbox"
                  disabled={props.disabled}
                  aria-label={`${row.label || row.value} / ${column.label || column.value}`}
                  checked={selectedIn(row.value).includes(column.value)}
                  onChange={(event) => toggle(row.value, column.value, event.target.checked)}
                />
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  )
}

// -------------------------------------------------------------- repeatables

/** The add/remove frame every repeating widget shares. */
function Repeater({
  props,
  entries,
  onAdd,
  children,
}: {
  props: WidgetProps
  entries: unknown[]
  onAdd: () => void
  children: (entry: unknown, index: number) => ReactNode
}) {
  const { addLabel, maxEntries } = propsOf<{ addLabel: string; maxEntries: number }>(
    props.question,
  )
  const full = maxEntries !== undefined && entries.length >= maxEntries
  return (
    <div className="vqf-repeater">
      {entries.map((entry, index) => (
        <div className="vqf-repeater__entry" key={index}>
          <div className="vqf-repeater__body">{children(entry, index)}</div>
          <button
            type="button"
            className="vqf-repeater__remove"
            disabled={props.disabled}
            title={props.t("widget.repeater.remove", { position: index + 1 })}
            onClick={() => props.onChange(entries.filter((_, position) => position !== index))}
          >
            ×
          </button>
        </div>
      ))}
      {entries.length ? null : <p className="vqf-empty">{props.t("widget.repeater.empty")}</p>}
      <button
        type="button"
        className="vqf-repeater__add"
        disabled={props.disabled || full}
        onClick={onAdd}
      >
        {addLabel || props.t("widget.repeater.add")}
      </button>
    </div>
  )
}

function ItemListWidget(props: WidgetProps) {
  const entries = asList(props.value)
  // Each entry is a scalar of the list's item type, so it is rendered by
  // whatever renders that type -- the same registry, one level down.
  const item: QuestionPlan = {
    ...props.question,
    type: props.question.itemType || "free_text",
    widget: null,
    widgetProps: {},
    choices: props.question.choices,
  }
  const Item = resolveWidget(item) ?? TextWidget

  return (
    <Repeater props={props} entries={entries} onAdd={() => props.onChange([...entries, null])}>
      {(entry, index) => (
        <Item
          {...props}
          question={item}
          id={`${props.id}-${index}`}
          errors={[]}
          value={entry}
          onChange={(next) =>
            props.onChange(
              entries.map((other, position) => (position === index ? next : other)),
            )
          }
        />
      )}
    </Repeater>
  )
}

/** The questions of a nested questionnaire, flattened -- it is one answer set. */
function nestedQuestions(question: QuestionPlan): QuestionPlan[] {
  const sub = question.subQuestionnaire
  if (!isExpandedSubQuestionnaire(sub)) return []
  return sub.pages.flatMap((page) => page.sections.flatMap((section) => section.questions))
}

function NestedAnswerSet({
  props,
  questions,
  answers,
  onChange,
  idPrefix,
}: {
  props: WidgetProps
  questions: QuestionPlan[]
  answers: Record<string, unknown>
  onChange: (answers: Record<string, unknown>) => void
  idPrefix: string
}) {
  return (
    <div className="vqf-nested">
      {questions.map((nested) => {
        const Nested = resolveWidget(nested) ?? TextWidget
        const id = `${idPrefix}-${nested.key}`
        return (
          <div className="vqf-part" key={nested.key}>
            <label className="vqf-part__label" htmlFor={id}>
              {nested.title}
            </label>
            <Nested
              {...props}
              question={nested}
              id={id}
              errors={[]}
              options={undefined}
              value={answers[nested.key]}
              onChange={(value) => onChange({ ...answers, [nested.key]: value })}
            />
          </div>
        )
      })}
      {questions.length ? null : (
        <p className="vqf-empty">{props.t("widget.nested.unresolved")}</p>
      )}
    </div>
  )
}

function SubQuestionnaireWidget(props: WidgetProps) {
  const questions = nestedQuestions(props.question)
  return (
    <NestedAnswerSet
      props={props}
      questions={questions}
      answers={asRecord(props.value)}
      onChange={props.onChange}
      idPrefix={props.id}
    />
  )
}

function RepeatableGroupWidget(props: WidgetProps) {
  const entries = asList(props.value)
  const questions = nestedQuestions(props.question)
  return (
    <Repeater props={props} entries={entries} onAdd={() => props.onChange([...entries, {}])}>
      {(entry, index) => (
        <NestedAnswerSet
          props={props}
          questions={questions}
          answers={asRecord(entry)}
          idPrefix={`${props.id}-${index}`}
          onChange={(answers) =>
            props.onChange(
              entries.map((other, position) => (position === index ? answers : other)),
            )
          }
        />
      )}
    </Repeater>
  )
}

// ---------------------------------------------------------------- installing

/**
 * The keys the package's own widgets answer to.
 *
 * Two families, registered from the one table. The question type keys are the
 * floor -- what renders a question whose widget nobody resolved. The widget
 * keys match the rows `install_default_widgets` creates on the server, so a
 * question that names one lands on the component of the same name.
 */
const DEFAULT_WIDGETS: [key: string, component: (props: WidgetProps) => ReactNode][] = [
  // -- by widget key
  ["input", TextWidget],
  ["textarea", TextAreaWidget],
  ["number-input", NumberWidget],
  ["radio-group", RadioGroupWidget],
  ["checkbox-group", CheckboxGroupWidget],
  ["select", SelectWidget],
  ["multi-select", MultiSelectWidget],
  ["date-input", TextWidget],
  ["time-input", TextWidget],
  ["month-input", TextWidget],
  ["year-input", NumberWidget],
  ["date-range", RangeWidget],
  ["number-range", RangeWidget],
  ["file-upload", FileWidget],
  ["matrix", MatrixWidget],
  ["item-list", ItemListWidget],
  ["sub-questionnaire", SubQuestionnaireWidget],
  ["repeatable-group", RepeatableGroupWidget],

  // -- by question type, for a question whose widget resolved to nothing
  ["free_text", TextWidget],
  ["url", TextWidget],
  ["number", NumberWidget],
  ["year", NumberWidget],
  ["time_duration", NumberWidget],
  ["time", TextWidget],
  ["date", TextWidget],
  ["date_time", TextWidget],
  ["month", TextWidget],
  ["single_choice", RadioGroupWidget],
  ["multiple_choice", CheckboxGroupWidget],
  ["single_select", SelectWidget],
  ["multi_select", MultiSelectWidget],
  ["number_range", RangeWidget],
  ["date_range", RangeWidget],
  ["date_time_range", RangeWidget],
  ["single_file", FileWidget],
  ["multiple_files", FileWidget],
  ["binary_matrix", MatrixWidget],
  ["item_list", ItemListWidget],
  ["sub_questionnaire", SubQuestionnaireWidget],
  ["sub_questionnaire_list", RepeatableGroupWidget],
]

for (const [key, component] of DEFAULT_WIDGETS) registerDefaultWidget(key, component)

/** The keys the package ships a component for. */
export const defaultWidgetKeys: readonly string[] = DEFAULT_WIDGETS.map(([key]) => key)

export {
  CheckboxGroupWidget,
  FileWidget,
  ItemListWidget,
  MatrixWidget,
  MultiSelectWidget,
  NumberWidget,
  RadioGroupWidget,
  RangeWidget,
  RepeatableGroupWidget,
  SelectWidget,
  SubQuestionnaireWidget,
  TextAreaWidget,
  TextWidget,
}
