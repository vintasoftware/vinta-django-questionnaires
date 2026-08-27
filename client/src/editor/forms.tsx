/**
 * The inspector: whatever is selected in the outline, as a form.
 *
 * Which fields a question shows follows the catalog rather than a list written
 * down here -- a type that takes no choices does not offer them, a validator's
 * params are rendered from its own schema -- so the editor keeps up with a
 * server that grows a question type or a validator without being changed.
 */

import type {
  ChoiceDefinition,
  DefinitionIssue,
  EditorCatalog,
  PageDefinition,
  QuestionDefinition,
  QuestionnaireDefinition,
  SectionDefinition,
  ValidatorDefinition,
} from "../definition.js"
import {
  defaultWidgetFor,
  questionTypeInfo,
  validatorInfo,
  validatorsFor,
  widgetsFor,
} from "../definition.js"
import {
  issuesAt,
  pathOf,
  slugify,
  type EditorAction,
  type NodePath,
  type QuestionPath,
  type SectionPath,
} from "../editorState.js"
import { SchemaForm } from "./SchemaForm.js"
import { DragHandle, SortableItem, SortableList, type HandleProps } from "./Sortable.js"
import { Button, Checkbox, Errors, NumberInput, Select, TextArea, TextInput } from "./fields.js"

const KEY_HINT =
  "Answers are stored against this. Changing it orphans the answers already given."

/** The keys `newPage`, `newSection` and `newQuestion` hand out. */
const GENERATED_KEY = /^(page|section|question)(-\d+)?$/

interface Common {
  catalog: EditorCatalog | null
  issues: readonly DefinitionIssue[]
  dispatch: (action: EditorAction) => void
}

// ------------------------------------------------------------------ version

export function VersionForm({
  document,
  catalog,
  issues,
  dispatch,
}: Common & { document: QuestionnaireDefinition }) {
  const errors = issuesAt(issues, "")
  const patch = (change: Partial<QuestionnaireDefinition>) =>
    dispatch({ type: "patchVersion", patch: change })

  return (
    <section className="vqe-form">
      <header className="vqe-form__header">
        <h2>
          {document.questionnaire.name} <span className="vqe-badge">v{document.version}</span>
        </h2>
        <p className="vqe-form__hint">
          {document.state?.responseCount
            ? `${document.state.responseCount} response(s) have already been given against this version.`
            : "No responses yet, so this version can still be changed freely."}
        </p>
      </header>

      <TextInput
        label="Title"
        value={document.title}
        errors={errors.title}
        onChange={(title) => patch({ title })}
      />
      <TextArea
        label="Description"
        hint="Markdown."
        value={document.description}
        errors={errors.description}
        onChange={(description) => patch({ description })}
      />
      <Select
        label="Status"
        value={document.status}
        options={catalog?.versionStatuses ?? []}
        errors={errors.status}
        onChange={(status) => patch({ status })}
      />
      <Select
        label="Edit policy"
        hint="Whether a respondent may come back and change what they answered."
        value={document.editPolicy}
        options={catalog?.editPolicies ?? []}
        errors={errors.edit_policy}
        onChange={(editPolicy) => patch({ editPolicy })}
      />
      <TextInput
        label="Responses due at"
        hint="ISO 8601, e.g. 2026-12-31T23:59:00Z. Empty for no deadline."
        value={document.responsesDueAt ?? ""}
        errors={errors.responsesDueAt ?? errors.responses_due_at}
        onChange={(value) => patch({ responsesDueAt: value || null })}
      />
      <TextInput
        label="Edits due at"
        value={document.editsDueAt ?? ""}
        errors={errors.editsDueAt ?? errors.edits_due_at}
        onChange={(value) => patch({ editsDueAt: value || null })}
      />

      <RangeList document={document} issues={issues} dispatch={dispatch} />
      <ColumnsField
        label="Columns of the questionnaire's grid"
        hint="What every page inherits unless it says otherwise."
        document={document}
        columns={document.columns}
        path={null}
        errors={issuesAt(issues, "columns")}
        dispatch={dispatch}
      />
    </section>
  )
}

function RangeList({
  document,
  issues,
  dispatch,
}: {
  document: QuestionnaireDefinition
  issues: readonly DefinitionIssue[]
  dispatch: (action: EditorAction) => void
}) {
  return (
    <fieldset className="vqe-fieldset">
      <legend className="vqe-fieldset__legend">Window size ranges</legend>
      <p className="vqe-form__hint">
        The breakpoints this questionnaire is laid out against. Every column count below is
        keyed by one of them.
      </p>
      {document.windowSizeRanges.map((range, index) => {
        const errors = issuesAt(issues, `windowSizeRanges.${index}`)
        return (
          <div className="vqe-row" key={index}>
            <TextInput
              label="Key"
              value={range.key}
              errors={errors.key}
              onChange={(key) => dispatch({ type: "patchRange", index, patch: { key } })}
            />
            <TextInput
              label="Label"
              value={range.label}
              errors={errors.label}
              onChange={(label) => dispatch({ type: "patchRange", index, patch: { label } })}
            />
            <NumberInput
              label="From (px)"
              min={0}
              value={range.minWidth}
              errors={errors.min_width}
              onChange={(minWidth) =>
                dispatch({
                  type: "patchRange",
                  index,
                  patch: { minWidth: minWidth ?? 0 },
                })
              }
            />
            <NumberInput
              label="To (px)"
              min={0}
              placeholder="unbounded"
              value={range.maxWidth}
              errors={errors.max_width}
              onChange={(maxWidth) =>
                dispatch({ type: "patchRange", index, patch: { maxWidth } })
              }
            />
            <Button variant="danger" onClick={() => dispatch({ type: "removeRange", index })}>
              Remove
            </Button>
          </div>
        )
      })}
      <Button variant="quiet" onClick={() => dispatch({ type: "insertRange" })}>
        + Window size range
      </Button>
    </fieldset>
  )
}

// -------------------------------------------------------------------- pages

export function PageForm({
  page,
  path,
  document,
  issues,
  dispatch,
}: Common & {
  page: PageDefinition
  path: NodePath
  document: QuestionnaireDefinition
}) {
  const errors = issuesAt(issues, pathOf(path))
  const patch = (change: Partial<PageDefinition>) =>
    dispatch({ type: "patch", path, patch: change })

  return (
    <section className="vqe-form">
      <header className="vqe-form__header">
        <h2>Page</h2>
      </header>
      <KeyAndTitle
        keyValue={page.key}
        title={page.title}
        errors={errors}
        onKey={(key) => patch({ key })}
        onTitle={(title) => patch({ title })}
      />
      <TextArea
        label="Description"
        hint="Markdown, shown at the top of the page."
        value={page.description}
        errors={errors.description}
        onChange={(description) => patch({ description })}
      />
      <TextArea
        label="Conclusion"
        hint="Markdown, shown once the page is filled in."
        value={page.conclusion}
        errors={errors.conclusion}
        onChange={(conclusion) => patch({ conclusion })}
      />
      <ConditionField
        value={page.condition}
        errors={errors.condition}
        onChange={(condition) => patch({ condition })}
      />
      <Checkbox
        label="Skippable"
        hint="Whether the respondent may leave this page for later and move on."
        checked={page.isSkippable}
        errors={errors.is_skippable}
        onChange={(isSkippable) => patch({ isSkippable })}
      />
      <ColumnsField
        label="Columns of this page's grid"
        hint="Empty inherits from the questionnaire."
        document={document}
        columns={page.columns}
        path={path}
        errors={issuesAt(issues, `${pathOf(path)}.columns`)}
        dispatch={dispatch}
      />
    </section>
  )
}

export function SectionForm({
  section,
  path,
  document,
  catalog,
  issues,
  dispatch,
}: Common & {
  section: SectionDefinition
  path: SectionPath
  document: QuestionnaireDefinition
}) {
  const errors = issuesAt(issues, pathOf(path))
  const patch = (change: Partial<SectionDefinition>) =>
    dispatch({ type: "patch", path, patch: change })

  return (
    <section className="vqe-form">
      <header className="vqe-form__header">
        <h2>Section</h2>
      </header>
      <KeyAndTitle
        keyValue={section.key}
        title={section.title}
        errors={errors}
        onKey={(key) => patch({ key })}
        onTitle={(title) => patch({ title })}
      />
      <TextArea
        label="Description"
        hint="Markdown."
        value={section.description}
        errors={errors.description}
        onChange={(description) => patch({ description })}
      />
      <TextArea
        label="Conclusion"
        hint="Markdown."
        value={section.conclusion}
        errors={errors.conclusion}
        onChange={(conclusion) => patch({ conclusion })}
      />
      <Select
        label="Default state"
        hint="Whether the section starts open or collapsed."
        value={section.defaultState}
        options={catalog?.sectionStates ?? []}
        errors={errors.default_state}
        onChange={(value) =>
          patch({ defaultState: value as SectionDefinition["defaultState"] })
        }
      />
      <ConditionField
        value={section.condition}
        errors={errors.condition}
        onChange={(condition) => patch({ condition })}
      />
      <ColumnsField
        label="Columns of this section's grid"
        hint="Empty inherits from the page."
        document={document}
        columns={section.columns}
        path={path}
        errors={issuesAt(issues, `${pathOf(path)}.columns`)}
        dispatch={dispatch}
      />
    </section>
  )
}

// ---------------------------------------------------------------- questions

export function QuestionForm({
  question,
  path,
  document,
  catalog,
  issues,
  dispatch,
}: Common & {
  question: QuestionDefinition
  path: QuestionPath
  document: QuestionnaireDefinition
}) {
  const base = pathOf(path)
  const errors = issuesAt(issues, base)
  const patch = (change: Partial<QuestionDefinition>) =>
    dispatch({ type: "patch", path, patch: change })
  const info = catalog ? questionTypeInfo(catalog, question.questionType) : undefined
  const widget = catalog
    ? question.widget
      ? catalog.widgets.find((entry) => entry.key === question.widget)
      : defaultWidgetFor(catalog, question.questionType)
    : undefined

  return (
    <section className="vqe-form">
      <header className="vqe-form__header">
        <h2>Question</h2>
        {question.resolved?.fingerprint ? (
          <p className="vqe-form__hint">
            Fingerprint <code>{question.resolved.fingerprint.slice(0, 12)}</code> -- answers
            from another version pool with this question while it stays the same.
          </p>
        ) : null}
      </header>

      <KeyAndTitle
        keyValue={question.key}
        title={question.title}
        errors={errors}
        onKey={(key) => patch({ key })}
        onTitle={(title) => patch({ title })}
      />
      <TextArea
        label="Description"
        hint="Markdown."
        value={question.description}
        errors={errors.description}
        onChange={(description) => patch({ description })}
      />
      <Select
        label="Question type"
        value={question.questionType}
        options={(catalog?.questionTypes ?? []).map((entry) => ({
          value: entry.key,
          label: entry.label,
        }))}
        errors={errors.question_type ?? errors.questionType}
        onChange={(questionType) => patch({ questionType })}
      />

      {info?.requiresItemType ? (
        <Select
          label="Item type"
          hint="The type of each entry of the list."
          value={question.itemQuestionType}
          emptyLabel="--"
          options={(catalog?.questionTypes ?? [])
            .filter((entry) => catalog?.scalarQuestionTypes.includes(entry.key))
            .map((entry) => ({ value: entry.key, label: entry.label }))}
          errors={errors.item_question_type ?? errors.itemQuestionType}
          onChange={(itemQuestionType) => patch({ itemQuestionType })}
        />
      ) : null}

      {info?.requiresSubQuestionnaire ? (
        <>
          <Select
            label="Sub-questionnaire"
            value={question.subQuestionnaire ?? ""}
            emptyLabel="--"
            options={(catalog?.questionnaires ?? []).map((entry) => ({
              value: entry.key,
              label: entry.name,
            }))}
            errors={errors.sub_questionnaire ?? errors.subQuestionnaire}
            onChange={(value) =>
              patch({
                subQuestionnaire: value || null,
                subQuestionnaireVersion: null,
              })
            }
          />
          <Select
            label="Pinned version"
            hint="Empty follows whichever version of it is published."
            value={question.subQuestionnaireVersion?.toString() ?? ""}
            emptyLabel="Latest published"
            options={(
              catalog?.questionnaires.find((entry) => entry.key === question.subQuestionnaire)
                ?.versions ?? []
            ).map((entry) => ({
              value: String(entry.version),
              label: `v${entry.version} -- ${entry.title} (${entry.status})`,
            }))}
            errors={errors.sub_questionnaire_version ?? errors.subQuestionnaireVersion}
            onChange={(value) =>
              patch({ subQuestionnaireVersion: value ? Number(value) : null })
            }
          />
        </>
      ) : null}

      {info?.supportsValueSet ? (
        <Select
          label="Value set"
          hint={
            info.supportsChoices
              ? "Where the options come from, instead of the inline choices below."
              : "Where the options come from."
          }
          value={question.valueSet ?? ""}
          emptyLabel="--"
          options={(catalog?.valueSets ?? []).map((entry) => ({
            value: entry.key,
            label: entry.name,
          }))}
          errors={errors.value_set ?? errors.valueSet}
          onChange={(value) => patch({ valueSet: value || null })}
        />
      ) : null}

      {info?.supportsOtherOption ? (
        <>
          <Checkbox
            label="Allows an other option"
            hint="Adds a free text escape hatch to the choices."
            checked={question.allowsOther}
            errors={errors.allows_other ?? errors.allowsOther}
            onChange={(allowsOther) => patch({ allowsOther })}
          />
          {question.allowsOther ? (
            <TextInput
              label="Other label"
              value={question.otherLabel}
              errors={errors.other_label}
              onChange={(otherLabel) => patch({ otherLabel })}
            />
          ) : null}
        </>
      ) : null}

      <ConditionField
        value={question.condition}
        errors={errors.condition}
        onChange={(condition) => patch({ condition })}
      />

      <fieldset className="vqe-fieldset">
        <legend className="vqe-fieldset__legend">Layout</legend>
        <Checkbox
          label="Must be first in its row"
          checked={question.requiresBeingFirstInARow}
          onChange={(value) => patch({ requiresBeingFirstInARow: value })}
        />
        <Checkbox
          label="Must be last in its row"
          checked={question.requiresBeingLastInARow}
          onChange={(value) => patch({ requiresBeingLastInARow: value })}
        />
        <MinimumColumnsField
          document={document}
          question={question}
          path={path}
          errors={issuesAt(issues, `${base}.minimumColumns`)}
          dispatch={dispatch}
        />
      </fieldset>

      <fieldset className="vqe-fieldset">
        <legend className="vqe-fieldset__legend">Widget</legend>
        <Select
          label="Widget"
          hint={
            question.widget
              ? "The component the client renders this with."
              : `Empty uses the type's default${widget ? `, which is ${widget.name}` : ""}.`
          }
          value={question.widget ?? ""}
          emptyLabel="Default for the type"
          options={(catalog ? widgetsFor(catalog, question.questionType) : []).map((entry) => ({
            value: entry.key,
            label: entry.name,
          }))}
          errors={errors.widget}
          onChange={(value) => patch({ widget: value || null })}
        />
        <SchemaForm
          label="Widget props"
          schema={widget?.propsSchema}
          value={question.widgetProps}
          errors={errors.widget_props ?? errors.widgetProps}
          onChange={(widgetProps) => patch({ widgetProps })}
        />
      </fieldset>

      {info?.supportsChoices ? (
        <ChoiceList
          question={question}
          path={path}
          matrix={info.usesMatrixAxes}
          issues={issues}
          catalog={catalog}
          dispatch={dispatch}
        />
      ) : null}

      <ValidatorList
        question={question}
        path={path}
        issues={issues}
        catalog={catalog}
        dispatch={dispatch}
      />
    </section>
  )
}

// ------------------------------------------------------------------ choices

function ChoiceList({
  question,
  path,
  matrix,
  issues,
  catalog,
  dispatch,
}: Common & {
  question: QuestionDefinition
  path: QuestionPath
  matrix: boolean
}) {
  const base = pathOf(path)
  const axes = matrix
    ? (catalog?.choiceAxes ?? []).filter((axis) => axis.value !== "option")
    : (catalog?.choiceAxes ?? []).filter((axis) => axis.value === "option")

  return (
    <fieldset className="vqe-fieldset">
      <legend className="vqe-fieldset__legend">
        {matrix ? "Rows and columns" : "Choices"}
      </legend>
      <Errors errors={issuesAt(issues, base).choices} />
      <SortableList
        label="choices"
        ids={question.choices.map((choice, index) => `${choice.axis}:${choice.value}:${index}`)}
        onReorder={(from, to) =>
          dispatch({ type: "reorderItem", path, list: "choices", from, to })
        }
      >
        {question.choices.map((choice, index) => {
          const errors = issuesAt(issues, `${base}.choices.${index}`)
          const id = `${choice.axis}:${choice.value}:${index}`
          return (
            <SortableItem key={id} id={id}>
              {(handle) => (
                <div className="vqe-row">
                  <DragHandle
                    handle={handle}
                    label={`choice ${choice.label || choice.value}`}
                  />
                  {matrix ? (
                    <Select
                      label="Axis"
                      value={choice.axis}
                      options={axes}
                      errors={errors.axis}
                      onChange={(axis) =>
                        dispatch({
                          type: "patchItem",
                          path,
                          list: "choices",
                          index,
                          patch: { axis: axis as ChoiceDefinition["axis"] },
                        })
                      }
                    />
                  ) : null}
                  <TextInput
                    label="Value"
                    hint={index === 0 ? "What is stored in the answer." : undefined}
                    value={choice.value}
                    errors={errors.value}
                    onChange={(value) =>
                      dispatch({
                        type: "patchItem",
                        path,
                        list: "choices",
                        index,
                        patch: { value },
                      })
                    }
                  />
                  <TextInput
                    label="Label"
                    value={choice.label}
                    errors={errors.label}
                    onChange={(label) =>
                      dispatch({
                        type: "patchItem",
                        path,
                        list: "choices",
                        index,
                        patch: { label },
                      })
                    }
                  />
                  <Checkbox
                    label="Active"
                    checked={choice.isActive}
                    onChange={(isActive) =>
                      dispatch({
                        type: "patchItem",
                        path,
                        list: "choices",
                        index,
                        patch: { isActive },
                      })
                    }
                  />
                  <RemoveButton
                    label="choice"
                    onRemove={() =>
                      dispatch({
                        type: "removeItem",
                        path,
                        list: "choices",
                        index,
                      })
                    }
                  />
                </div>
              )}
            </SortableItem>
          )
        })}
      </SortableList>
      <Button
        variant="quiet"
        onClick={() => dispatch({ type: "insertItem", path, list: "choices" })}
      >
        + Choice
      </Button>
    </fieldset>
  )
}

// --------------------------------------------------------------- validators

function ValidatorList({
  question,
  path,
  issues,
  catalog,
  dispatch,
}: Common & { question: QuestionDefinition; path: QuestionPath }) {
  const base = pathOf(path)
  const applicable = catalog ? validatorsFor(catalog, question.questionType) : []

  return (
    <fieldset className="vqe-fieldset">
      <legend className="vqe-fieldset__legend">Validators</legend>
      <p className="vqe-form__hint">
        They run in this order, and each one sees what the ones before it recorded.
      </p>
      <SortableList
        label="validators"
        ids={question.validators.map((binding, index) => `${binding.validator}:${index}`)}
        onReorder={(from, to) =>
          dispatch({ type: "reorderItem", path, list: "validators", from, to })
        }
      >
        {question.validators.map((binding, index) => (
          <SortableItem
            key={`${binding.validator}:${index}`}
            id={`${binding.validator}:${index}`}
          >
            {(handle) => (
              <ValidatorRow
                handle={handle}
                binding={binding}
                index={index}
                path={path}
                applicable={applicable}
                info={catalog ? validatorInfo(catalog, binding.validator) : undefined}
                errors={issuesAt(issues, `${base}.validators.${index}`)}
                dispatch={dispatch}
              />
            )}
          </SortableItem>
        ))}
      </SortableList>
      <Button
        variant="quiet"
        onClick={() => dispatch({ type: "insertItem", path, list: "validators" })}
      >
        + Validator
      </Button>
    </fieldset>
  )
}

function ValidatorRow({
  handle,
  binding,
  index,
  path,
  applicable,
  info,
  errors,
  dispatch,
}: {
  handle: HandleProps
  binding: ValidatorDefinition
  index: number
  path: QuestionPath
  applicable: ReturnType<typeof validatorsFor>
  info: ReturnType<typeof validatorInfo>
  errors: Record<string, string[]>
  dispatch: (action: EditorAction) => void
}) {
  const patch = (change: Partial<ValidatorDefinition>) =>
    dispatch({
      type: "patchItem",
      path,
      list: "validators",
      index,
      patch: change,
    })

  return (
    <div className="vqe-card">
      <div className="vqe-row">
        <DragHandle handle={handle} label={`validator ${binding.validator}`} />
        <Select
          label={`${index + 1}.`}
          value={binding.validator}
          options={applicable.map((entry) => ({
            value: entry.key,
            label: entry.label,
          }))}
          errors={errors.validator}
          onChange={(validator) => patch({ validator, params: {}, messageOverrides: {} })}
        />
        <Checkbox
          label="Enabled"
          checked={binding.isEnabled}
          onChange={(isEnabled) => patch({ isEnabled })}
        />
        <RemoveButton
          label="validator"
          onRemove={() => dispatch({ type: "removeItem", path, list: "validators", index })}
        />
      </div>

      {info ? (
        <>
          <p className="vqe-form__hint">
            {info.description}
            {info.clientMode === "server_only" ? (
              <strong> Checked on submit only -- the browser cannot run it.</strong>
            ) : null}
            {info.clientMode === "custom" ? (
              <strong>
                {" "}
                Needs an implementation registered under the same key in the browser.
              </strong>
            ) : null}
          </p>
          <SchemaForm
            label="Params"
            schema={info.paramsSchema}
            value={binding.params}
            errors={errors.params}
            onChange={(params) => patch({ params })}
          />
          <fieldset className="vqe-fieldset vqe-fieldset--tight">
            <legend className="vqe-fieldset__legend">Messages</legend>
            {info.errorKeys.map((error) => (
              <TextInput
                key={error.key}
                label={error.key}
                placeholder={error.message}
                value={binding.messageOverrides[error.key] ?? ""}
                onChange={(message) => {
                  const overrides = { ...binding.messageOverrides }
                  if (message) overrides[error.key] = message
                  else delete overrides[error.key]
                  patch({ messageOverrides: overrides })
                }}
              />
            ))}
            <Errors errors={errors.message_overrides} />
          </fieldset>
        </>
      ) : null}
    </div>
  )
}

// ------------------------------------------------------------------- shared

function KeyAndTitle({
  keyValue,
  title,
  errors,
  onKey,
  onTitle,
}: {
  keyValue: string
  title: string
  errors: Record<string, string[]>
  onKey: (key: string) => void
  onTitle: (title: string) => void
}) {
  return (
    <div className="vqe-row">
      <TextInput
        label="Title"
        value={title}
        errors={errors.title}
        onChange={(next) => {
          onTitle(next)
          // The key follows the title only while it is still the one the editor
          // generated. Once someone has a key of their own, it is left alone --
          // answers are stored against it, and rewriting it would orphan them.
          if (!keyValue || GENERATED_KEY.test(keyValue)) {
            const derived = slugify(next)
            if (derived) onKey(derived)
          }
        }}
      />
      <TextInput
        label="Key"
        hint={KEY_HINT}
        monospace
        value={keyValue}
        errors={errors.key}
        onChange={onKey}
      />
    </div>
  )
}

function ConditionField({
  value,
  errors,
  onChange,
}: {
  value: string
  errors?: string[]
  onChange: (value: string) => void
}) {
  return (
    <TextInput
      label="Condition"
      hint="A JMESPath expression over the answers so far. Empty always applies."
      monospace
      placeholder="e.g. has_company"
      value={value}
      errors={errors}
      onChange={onChange}
    />
  )
}

function ColumnsField({
  label,
  hint,
  document,
  columns,
  path,
  errors,
  dispatch,
}: {
  label: string
  hint: string
  document: QuestionnaireDefinition
  columns: Record<string, number>
  path: NodePath | null
  errors: Record<string, string[]>
  dispatch: (action: EditorAction) => void
}) {
  if (!document.windowSizeRanges.length) return null
  return (
    <fieldset className="vqe-fieldset vqe-fieldset--tight">
      <legend className="vqe-fieldset__legend">{label}</legend>
      <p className="vqe-form__hint">{hint}</p>
      <div className="vqe-row">
        {document.windowSizeRanges.map((range) => (
          <NumberInput
            key={range.key}
            label={range.label || range.key}
            min={1}
            placeholder="inherit"
            value={columns[range.key] ?? null}
            errors={errors[range.key]}
            onChange={(value) =>
              dispatch({
                type: "setColumns",
                path,
                range: range.key,
                columns: value,
              })
            }
          />
        ))}
      </div>
    </fieldset>
  )
}

function MinimumColumnsField({
  document,
  question,
  path,
  errors,
  dispatch,
}: {
  document: QuestionnaireDefinition
  question: QuestionDefinition
  path: QuestionPath
  errors: Record<string, string[]>
  dispatch: (action: EditorAction) => void
}) {
  if (!document.windowSizeRanges.length) return null
  return (
    <fieldset className="vqe-fieldset vqe-fieldset--tight">
      <legend className="vqe-fieldset__legend">Minimum columns</legend>
      <p className="vqe-form__hint">
        The narrowest this question may be rendered in each range. Empty takes the default.
      </p>
      <div className="vqe-row">
        {document.windowSizeRanges.map((range) => (
          <NumberInput
            key={range.key}
            label={range.label || range.key}
            min={1}
            placeholder="default"
            value={question.minimumColumns[range.key] ?? null}
            errors={errors[range.key]}
            onChange={(value) =>
              dispatch({
                type: "setMinimumColumns",
                path,
                range: range.key,
                columns: value,
              })
            }
          />
        ))}
      </div>
    </fieldset>
  )
}

function RemoveButton({ label, onRemove }: { label: string; onRemove: () => void }) {
  return (
    <span className="vqe-item-controls">
      <button type="button" title={`Remove this ${label}`} onClick={onRemove}>
        ×
      </button>
    </span>
  )
}
