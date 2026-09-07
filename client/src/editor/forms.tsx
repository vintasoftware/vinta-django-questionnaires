/**
 * The inspector: whatever is selected in the outline, as a form.
 *
 * Which fields a question shows follows the catalog rather than a list written
 * down here -- a type that takes no choices does not offer them, a validator's
 * params are rendered from its own schema -- so the editor keeps up with a
 * server that grows a question type or a validator without being changed.
 */

import { useState, type ReactNode } from "react"

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
import { NoRanges, RangeStrips, STANDARD_RANGES } from "./ColumnPicker.js"
import { columnsFor, DEFAULT_COLUMN_COUNT } from "../widgets/grid.js"
import { SchemaForm } from "./SchemaForm.js"
import { DragHandle, SortableItem, SortableList, type HandleProps } from "./Sortable.js"
import { Button, Checkbox, Errors, NumberInput, Select, TextArea, TextInput } from "./fields.js"
import { useStrings, type WithStrings } from "./strings.js"
import type { Translate } from "../strings.js"

/** The widest grid a layer may declare. Past this a strip stops being readable. */
const MAX_GRID_COLUMNS = 24

interface Common extends WithStrings {
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
  strings,
}: Common & { document: QuestionnaireDefinition }) {
  const t = useStrings(strings)
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
            ? t("version.responses", { count: document.state.responseCount })
            : t("version.noResponses")}
        </p>
      </header>

      <TextInput
        label={t("field.title")}
        value={document.title}
        errors={errors.title}
        onChange={(title) => patch({ title })}
      />
      <TextArea
        label={t("field.description")}
        hint={t("field.markdownHint")}
        value={document.description}
        errors={errors.description}
        onChange={(description) => patch({ description })}
      />
      <Select
        label={t("version.status")}
        value={document.status}
        options={catalog?.versionStatuses ?? []}
        errors={errors.status}
        onChange={(status) => patch({ status })}
      />
      <Select
        label={t("version.editPolicy")}
        hint={t("version.editPolicyHint")}
        value={document.editPolicy}
        options={catalog?.editPolicies ?? []}
        errors={errors.edit_policy}
        onChange={(editPolicy) => patch({ editPolicy })}
      />
      <TextInput
        label={t("version.responsesDueAt")}
        hint={t("version.dueAtHint")}
        value={document.responsesDueAt ?? ""}
        errors={errors.responsesDueAt ?? errors.responses_due_at}
        onChange={(value) => patch({ responsesDueAt: value || null })}
      />
      <TextInput
        label={t("version.editsDueAt")}
        value={document.editsDueAt ?? ""}
        errors={errors.editsDueAt ?? errors.edits_due_at}
        onChange={(value) => patch({ editsDueAt: value || null })}
      />

      <RangeList document={document} issues={issues} dispatch={dispatch} t={t} />
      <ColumnsField
        t={t}
        label={t("version.columns")}
        hint={t("version.columnsHint")}
        document={document}
        columns={document.columns}
        inherited={() => DEFAULT_COLUMN_COUNT}
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
  t,
}: {
  document: QuestionnaireDefinition
  issues: readonly DefinitionIssue[]
  dispatch: (action: EditorAction) => void
  t: Translate
}) {
  return (
    <fieldset className="vqe-fieldset">
      <legend className="vqe-fieldset__legend">{t("ranges.legend")}</legend>
      <p className="vqe-form__hint">{t("ranges.hint")}</p>
      {document.windowSizeRanges.map((range, index) => {
        const errors = issuesAt(issues, `windowSizeRanges.${index}`)
        return (
          <div className="vqe-row" key={index}>
            <TextInput
              label={t("field.key")}
              value={range.key}
              errors={errors.key}
              onChange={(key) => dispatch({ type: "patchRange", index, patch: { key } })}
            />
            <TextInput
              label={t("field.label")}
              value={range.label}
              errors={errors.label}
              onChange={(label) => dispatch({ type: "patchRange", index, patch: { label } })}
            />
            <NumberInput
              label={t("ranges.from")}
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
              label={t("ranges.to")}
              min={0}
              placeholder={t("ranges.unbounded")}
              value={range.maxWidth}
              errors={errors.max_width}
              onChange={(maxWidth) =>
                dispatch({ type: "patchRange", index, patch: { maxWidth } })
              }
            />
            <Button variant="danger" onClick={() => dispatch({ type: "removeRange", index })}>
              {t("field.remove")}
            </Button>
          </div>
        )
      })}
      <Button variant="quiet" onClick={() => dispatch({ type: "insertRange" })}>
        {t("ranges.add")}
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
  strings,
}: Common & {
  page: PageDefinition
  path: NodePath
  document: QuestionnaireDefinition
}) {
  const t = useStrings(strings)
  const errors = issuesAt(issues, pathOf(path))
  const patch = (change: Partial<PageDefinition>) =>
    dispatch({ type: "patch", path, patch: change })

  return (
    <section className="vqe-form">
      <header className="vqe-form__header">
        <h2>{t("page.heading")}</h2>
      </header>
      <KeyAndTitle
        t={t}
        kind="page"
        isNew={!!page.isNew}
        keyValue={page.key}
        title={page.title}
        errors={errors}
        onKey={(key) => patch({ key })}
        onTitle={(title) => patch({ title })}
      />
      <TextArea
        label={t("field.description")}
        hint={t("page.descriptionHint")}
        value={page.description}
        errors={errors.description}
        onChange={(description) => patch({ description })}
      />
      <TextArea
        label={t("field.conclusion")}
        hint={t("page.conclusionHint")}
        value={page.conclusion}
        errors={errors.conclusion}
        onChange={(conclusion) => patch({ conclusion })}
      />
      <ConditionField
        t={t}
        value={page.condition}
        errors={errors.condition}
        onChange={(condition) => patch({ condition })}
      />
      <Checkbox
        label={t("page.skippable")}
        hint={t("page.skippableHint")}
        checked={page.isSkippable}
        errors={errors.is_skippable}
        onChange={(isSkippable) => patch({ isSkippable })}
      />
      <ColumnsField
        t={t}
        label={t("page.columns")}
        hint={t("page.columnsHint")}
        document={document}
        columns={page.columns}
        inherited={(range) => columnsFor([document.columns], range)}
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
  strings,
}: Common & {
  section: SectionDefinition
  path: SectionPath
  document: QuestionnaireDefinition
}) {
  const t = useStrings(strings)
  const errors = issuesAt(issues, pathOf(path))
  const patch = (change: Partial<SectionDefinition>) =>
    dispatch({ type: "patch", path, patch: change })

  return (
    <section className="vqe-form">
      <header className="vqe-form__header">
        <h2>{t("section.heading")}</h2>
      </header>
      <KeyAndTitle
        t={t}
        kind="section"
        isNew={!!section.isNew}
        keyValue={section.key}
        title={section.title}
        errors={errors}
        onKey={(key) => patch({ key })}
        onTitle={(title) => patch({ title })}
      />
      <TextArea
        label={t("field.description")}
        hint={t("field.markdownHint")}
        value={section.description}
        errors={errors.description}
        onChange={(description) => patch({ description })}
      />
      <TextArea
        label={t("field.conclusion")}
        hint={t("field.markdownHint")}
        value={section.conclusion}
        errors={errors.conclusion}
        onChange={(conclusion) => patch({ conclusion })}
      />
      <Select
        label={t("section.defaultState")}
        hint={t("section.defaultStateHint")}
        value={section.defaultState}
        options={catalog?.sectionStates ?? []}
        errors={errors.default_state}
        onChange={(value) =>
          patch({ defaultState: value as SectionDefinition["defaultState"] })
        }
      />
      <ConditionField
        t={t}
        value={section.condition}
        errors={errors.condition}
        onChange={(condition) => patch({ condition })}
      />
      <ColumnsField
        t={t}
        label={t("section.columns")}
        hint={t("section.columnsHint")}
        document={document}
        columns={section.columns}
        inherited={(range) =>
          columnsFor([document.columns, document.pages[path.page]?.columns], range)
        }
        path={path}
        errors={issuesAt(issues, `${pathOf(path)}.columns`)}
        dispatch={dispatch}
      />
    </section>
  )
}

// ---------------------------------------------------------------- questions

/**
 * A question, as the six things there are to decide about one.
 *
 * It used to be every field of every kind, stacked, in one scroll -- which put
 * the choices of a multiple choice question below a widget's props schema and a
 * layout fieldset nobody had scrolled far enough to see. The groups below are
 * the actual decisions: what it is called, what it asks, when it applies, how
 * wide it is, what renders it, and what has to be true of the answer. Each one
 * remembers nothing and hides nothing -- a closed group says what is in it.
 */
export function QuestionForm({
  question,
  path,
  document,
  catalog,
  issues,
  dispatch,
  strings,
}: Common & {
  question: QuestionDefinition
  path: QuestionPath
  document: QuestionnaireDefinition
}) {
  const t = useStrings(strings)
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
        <h2>{t("question.heading")}</h2>
        {question.resolved?.fingerprint ? (
          <p className="vqe-form__hint">
            {t("question.fingerprint", {
              fingerprint: question.resolved.fingerprint.slice(0, 12),
            })}
          </p>
        ) : null}
      </header>

      <Group title={t("group.identity")} gist={question.key} open>
        <KeyAndTitle
          t={t}
          kind="question"
          isNew={!!question.isNew}
          keyValue={question.key}
          title={question.title}
          errors={errors}
          onKey={(key) => patch({ key })}
          onTitle={(title) => patch({ title })}
        />
        <TextArea
          label={t("field.description")}
          hint={t("field.markdownHint")}
          value={question.description}
          errors={errors.description}
          onChange={(description) => patch({ description })}
        />
      </Group>

      <Group title={t("group.behaviour")} gist={info?.label ?? question.questionType} open>
        <Select
          label={t("question.type")}
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
            label={t("question.itemType")}
            hint={t("question.itemTypeHint")}
            value={question.itemQuestionType}
            emptyLabel={t("field.empty")}
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
              label={t("question.subQuestionnaire")}
              value={question.subQuestionnaire ?? ""}
              emptyLabel={t("field.empty")}
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
              label={t("question.pinnedVersion")}
              hint={t("question.pinnedVersionHint")}
              value={question.subQuestionnaireVersion?.toString() ?? ""}
              emptyLabel={t("question.latestPublished")}
              options={(
                catalog?.questionnaires.find((entry) => entry.key === question.subQuestionnaire)
                  ?.versions ?? []
              ).map((entry) => ({
                value: String(entry.version),
                label: t("question.versionOption", {
                  version: entry.version,
                  title: entry.title,
                  status: entry.status,
                }),
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
            label={t("question.valueSet")}
            hint={t(
              info.supportsChoices
                ? "question.valueSetHintWithChoices"
                : "question.valueSetHint",
            )}
            value={question.valueSet ?? ""}
            emptyLabel={t("field.empty")}
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
              label={t("question.allowsOther")}
              hint={t("question.allowsOtherHint")}
              checked={question.allowsOther}
              errors={errors.allows_other ?? errors.allowsOther}
              onChange={(allowsOther) => patch({ allowsOther })}
            />
            {question.allowsOther ? (
              <TextInput
                label={t("question.otherLabel")}
                value={question.otherLabel}
                errors={errors.other_label}
                onChange={(otherLabel) => patch({ otherLabel })}
              />
            ) : null}
          </>
        ) : null}
      </Group>

      {info?.supportsChoices ? (
        <Group
          title={t(info.usesMatrixAxes ? "choices.matrixLegend" : "group.choices")}
          gist={t("choices.count", { count: question.choices.length })}
          open={question.choices.length > 0}
        >
          <ChoiceList
            question={question}
            path={path}
            matrix={info.usesMatrixAxes}
            issues={issues}
            catalog={catalog}
            dispatch={dispatch}
            t={t}
          />
        </Group>
      ) : null}

      <Group
        title={t("group.layout")}
        gist={layoutGist(t, document, question)}
        open={!!document.windowSizeRanges.length}
      >
        <MinimumColumnsField
          t={t}
          document={document}
          question={question}
          path={path}
          errors={issuesAt(issues, `${base}.minimumColumns`)}
          dispatch={dispatch}
        />
        <Checkbox
          label={t("question.firstInRow")}
          checked={question.requiresBeingFirstInARow}
          onChange={(value) => patch({ requiresBeingFirstInARow: value })}
        />
        <Checkbox
          label={t("question.lastInRow")}
          checked={question.requiresBeingLastInARow}
          onChange={(value) => patch({ requiresBeingLastInARow: value })}
        />
      </Group>

      <Group
        title={t("group.widget")}
        gist={widget?.name ?? t("question.widgetEmpty")}
        open={!!question.widget}
      >
        <Select
          label={t("question.widget")}
          hint={
            question.widget
              ? t("question.widgetHint")
              : widget
                ? t("question.widgetDefaultNamedHint", { name: widget.name })
                : t("question.widgetDefaultHint")
          }
          value={question.widget ?? ""}
          emptyLabel={t("question.widgetEmpty")}
          options={(catalog ? widgetsFor(catalog, question.questionType) : []).map((entry) => ({
            value: entry.key,
            label: entry.name,
          }))}
          errors={errors.widget}
          onChange={(value) => patch({ widget: value || null })}
        />
        <SchemaForm
          label={t("question.widgetProps")}
          schema={widget?.propsSchema}
          value={question.widgetProps}
          errors={errors.widget_props ?? errors.widgetProps}
          onChange={(widgetProps) => patch({ widgetProps })}
        />
      </Group>

      <Group
        title={t("group.rules")}
        gist={question.condition || t("field.conditionAlways")}
        open={!!question.condition}
      >
        <ConditionField
          t={t}
          value={question.condition}
          errors={errors.condition}
          onChange={(condition) => patch({ condition })}
        />
      </Group>

      <Group
        title={t("group.validators")}
        gist={t("validators.count", { count: question.validators.length })}
        open={question.validators.length > 0}
      >
        <ValidatorList
          question={question}
          path={path}
          issues={issues}
          catalog={catalog}
          dispatch={dispatch}
          t={t}
        />
      </Group>
    </section>
  )
}

/** What the layout group says while it is shut: the widths it is carrying. */
function layoutGist(
  t: Translate,
  document: QuestionnaireDefinition,
  question: QuestionDefinition,
): string {
  if (!document.windowSizeRanges.length) return t("columns.noRanges")
  const set = document.windowSizeRanges
    .filter((range) => question.minimumColumns[range.key] !== undefined)
    .map((range) => `${range.label || range.key} ${question.minimumColumns[range.key]}`)
  return set.length ? set.join(", ") : t("question.minimumColumnsPlaceholder")
}

// ------------------------------------------------------------------ choices

function ChoiceList({
  question,
  path,
  matrix,
  issues,
  catalog,
  dispatch,
  t,
}: Common & {
  question: QuestionDefinition
  path: QuestionPath
  matrix: boolean
  t: Translate
}) {
  const base = pathOf(path)
  const axes = matrix
    ? (catalog?.choiceAxes ?? []).filter((axis) => axis.value !== "option")
    : (catalog?.choiceAxes ?? []).filter((axis) => axis.value === "option")

  return (
    // No fieldset and no legend: this list is rendered inside a `Group` whose
    // summary is already the heading, and a second one under it said the same
    // word twice.
    <div className="vqe-list" role="group" aria-label={t("choices.listName")}>
      <Errors errors={issuesAt(issues, base).choices} />
      <SortableList
        label={t("choices.listName")}
        // Positional, so that editing a choice does not change the row's
        // identity: an id derived from the value would remount the row on
        // every keystroke and take the focus out of the field being typed in.
        ids={question.choices.map((_choice, index) => `choice-${index}`)}
        names={question.choices.map(
          (choice) => choice.label || choice.value || t("choices.blank"),
        )}
        onReorder={(from, to) =>
          dispatch({ type: "reorderItem", path, list: "choices", from, to })
        }
      >
        {question.choices.map((choice, index) => {
          const errors = issuesAt(issues, `${base}.choices.${index}`)
          const id = `choice-${index}`
          return (
            <SortableItem key={id} id={id}>
              {(handle) => (
                <div className="vqe-row">
                  <DragHandle
                    handle={handle}
                    label={t("choices.item", { name: choice.label || choice.value })}
                  />
                  {matrix ? (
                    <Select
                      label={t("choices.axis")}
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
                    label={t("choices.value")}
                    hint={index === 0 ? t("choices.valueHint") : undefined}
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
                    label={t("field.label")}
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
                    label={t("choices.active")}
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
                    title={t("choices.remove")}
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
        {t("choices.add")}
      </Button>
    </div>
  )
}

// --------------------------------------------------------------- validators

/**
 * The validator chain.
 *
 * A chain is the one list in the editor where order carries meaning -- each
 * link sees what the ones before it recorded -- so the position is numbered
 * rather than merely implied by where the card sits.
 *
 * Adding one names it up front. It used to hand out `required` and leave you to
 * change it, which is two steps to do one thing and reads as though the editor
 * had decided something on your behalf.
 */
function ValidatorList({
  question,
  path,
  issues,
  catalog,
  dispatch,
  t,
}: Common & { question: QuestionDefinition; path: QuestionPath; t: Translate }) {
  const base = pathOf(path)
  const applicable = catalog ? validatorsFor(catalog, question.questionType) : []

  return (
    <div className="vqe-list" role="group" aria-label={t("validators.legend")}>
      <p className="vqe-form__hint">{t("validators.hint")}</p>

      {question.validators.length ? (
        <SortableList
          label={t("validators.listName")}
          ids={question.validators.map((_binding, index) => `validator-${index}`)}
          names={question.validators.map((binding) => binding.validator)}
          onReorder={(from, to) =>
            dispatch({ type: "reorderItem", path, list: "validators", from, to })
          }
        >
          {question.validators.map((binding, index) => (
            <SortableItem key={`validator-${index}`} id={`validator-${index}`}>
              {(handle) => (
                <ValidatorRow
                  handle={handle}
                  binding={binding}
                  index={index}
                  count={question.validators.length}
                  path={path}
                  applicable={applicable}
                  info={catalog ? validatorInfo(catalog, binding.validator) : undefined}
                  errors={issuesAt(issues, `${base}.validators.${index}`)}
                  dispatch={dispatch}
                  t={t}
                />
              )}
            </SortableItem>
          ))}
        </SortableList>
      ) : (
        <p className="vqe-empty">{t("validators.none")}</p>
      )}

      <AddValidator
        applicable={applicable}
        taken={question.validators.map((binding) => binding.validator)}
        onAdd={(validator) =>
          dispatch({ type: "insertItem", path, list: "validators", validator })
        }
        t={t}
      />
    </div>
  )
}

/**
 * Pick which validator to add.
 *
 * A select rather than a button, because the interesting part of adding a
 * validator is *which*, and every applicable one is worth seeing at the moment
 * the question is being asked. It returns to its empty label after each pick,
 * so it reads as an action rather than as a field holding a value.
 *
 * The ones already on the chain stay listed but disabled: a chain with
 * `min_length` twice is not something to make easy, and a missing entry raises
 * the question of where it went.
 */
function AddValidator({
  applicable,
  taken,
  onAdd,
  t,
}: {
  applicable: ReturnType<typeof validatorsFor>
  taken: string[]
  onAdd: (validator: string) => void
  t: Translate
}) {
  return (
    <div className="vqe-add">
      <label className="vqe-add__label" htmlFor="vqe-add-validator">
        {t("validators.add")}
      </label>
      <select
        id="vqe-add-validator"
        className="vqe-input vqe-select vqe-add__select"
        value=""
        onChange={(event) => {
          if (event.target.value) onAdd(event.target.value)
        }}
      >
        <option value="">{t("validators.addEmpty")}</option>
        {applicable.map((entry) => (
          <option key={entry.key} value={entry.key} disabled={taken.includes(entry.key)}>
            {taken.includes(entry.key)
              ? t("validators.alreadyAdded", { label: entry.label })
              : entry.label}
          </option>
        ))}
      </select>
    </div>
  )
}

function ValidatorRow({
  handle,
  binding,
  index,
  count,
  path,
  applicable,
  info,
  errors,
  dispatch,
  t,
}: {
  handle: HandleProps
  t: Translate
  binding: ValidatorDefinition
  index: number
  count: number
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
  const name = info?.label || binding.validator
  const overrides = Object.keys(binding.messageOverrides).length

  return (
    <div className={`vqe-card vqe-chain${binding.isEnabled ? "" : " is-off"}`}>
      <div className="vqe-chain__head">
        <DragHandle handle={handle} label={t("validators.item", { name })} />
        {/* Numbered because the order is real: the chain runs in this order and
            each link reads what the ones before it recorded. */}
        <span className="vqe-chain__step" aria-hidden="true">
          {index + 1}
        </span>
        <span className="vqe-chain__name">
          <strong>{name}</strong>
          <span className="vqe-chain__position">
            {t("validators.position", { position: index + 1, count })}
          </span>
        </span>
        {info?.clientMode === "server_only" ? (
          <span className="vqe-badge" title={t("validators.serverOnly")}>
            {t("validators.serverOnlyBadge")}
          </span>
        ) : null}
        {info?.clientMode === "custom" ? (
          <span className="vqe-badge" title={t("validators.customMode")}>
            {t("validators.customBadge")}
          </span>
        ) : null}
        <Checkbox
          label={t("validators.enabled")}
          checked={binding.isEnabled}
          onChange={(isEnabled) => patch({ isEnabled })}
        />
        <Button
          variant="danger"
          onClick={() => dispatch({ type: "removeItem", path, list: "validators", index })}
        >
          {t("validators.remove")}
        </Button>
      </div>

      <Select
        label={t("validators.which")}
        value={binding.validator}
        options={applicable.map((entry) => ({ value: entry.key, label: entry.label }))}
        errors={errors.validator}
        // Params and message overrides belong to the validator that declared
        // them, so swapping which validator this is drops both rather than
        // handing the next one settings it never asked for.
        onChange={(validator) => patch({ validator, params: {}, messageOverrides: {} })}
      />

      {info ? (
        <>
          {info.description ? <p className="vqe-form__hint">{info.description}</p> : null}
          {info.clientMode === "server_only" ? (
            <p className="vqe-form__hint">{t("validators.serverOnly")}</p>
          ) : null}
          {info.clientMode === "custom" ? (
            <p className="vqe-form__hint">{t("validators.customMode")}</p>
          ) : null}

          <SchemaForm
            label={t("validators.params")}
            schema={info.paramsSchema}
            value={binding.params}
            errors={errors.params}
            onChange={(params) => patch({ params })}
          />

          {/* Shut by default. Every validator already carries a message, and
              most chains never override one, so an open fieldset of empty
              fields per error key is the noisiest thing on the form. */}
          {info.errorKeys.length ? (
            <details className="vqe-group vqe-group--nested" open={overrides > 0}>
              <summary className="vqe-group__summary">
                <span>{t("validators.messages")}</span>
                <span className="vqe-group__gist">
                  {overrides
                    ? t("validators.messagesOverridden", { count: overrides })
                    : t("validators.messagesDefault")}
                </span>
              </summary>
              <div className="vqe-group__body">
                {info.errorKeys.map((error) => (
                  <TextInput
                    key={error.key}
                    label={error.key}
                    monospace={false}
                    placeholder={error.message}
                    value={binding.messageOverrides[error.key] ?? ""}
                    onChange={(message) => {
                      const next = { ...binding.messageOverrides }
                      if (message) next[error.key] = message
                      else delete next[error.key]
                      patch({ messageOverrides: next })
                    }}
                  />
                ))}
                <Errors errors={errors.message_overrides} />
              </div>
            </details>
          ) : null}
        </>
      ) : (
        <Errors errors={[t("validators.unknown", { key: binding.validator })]} />
      )}
    </div>
  )
}

// ------------------------------------------------------------------- shared

/**
 * The title, and the key underneath it.
 *
 * The key used to sit beside the title as an equal field, which put the most
 * consequential value on the form -- answers are stored against it -- in front
 * of someone who mostly wants to name a question, and who has no reason to
 * touch it. It now writes itself from the title and shows as a line of help
 * text, with an Edit button for the times it does need changing.
 *
 * It follows the title until the node has been saved, and then stops for good.
 * That boundary is the whole rule: before a save nothing is stored against the
 * key, so rewriting it costs nothing; after one, answers are filed under it and
 * rewriting it would orphan every one of them. Editing the key by hand stops it
 * following too, since at that point the key is somebody's own.
 */
function KeyAndTitle({
  t,
  kind,
  isNew,
  keyValue,
  title,
  errors,
  onKey,
  onTitle,
}: {
  t: Translate
  /**
   * Which node this is, so the explanation under the field is the true one.
   *
   * The consequences differ: answers are filed under a *question* key, while a
   * page's is matched on save and recorded in a response's progress. One
   * sentence covering all three would have to be vague enough to be useless.
   */
  kind: "page" | "section" | "question"
  /** Whether the server has never seen this node. */
  isNew: boolean
  keyValue: string
  title: string
  errors: Record<string, string[]>
  onKey: (key: string) => void
  onTitle: (title: string) => void
}) {
  const [isEditing, setIsEditing] = useState(false)
  // Set by typing in the key field, never unset: a key somebody has written is
  // theirs, and going back to following the title would take it off them.
  const [isOwn, setIsOwn] = useState(false)
  const follows = isNew && !isOwn
  // Something was refused about the key, so the field has to be reachable --
  // an error under help text nobody can act on is worse than no error.
  const isShown = isEditing || !!errors.key?.length

  return (
    <>
      <TextInput
        label={t("field.title")}
        value={title}
        errors={errors.title}
        onChange={(next) => {
          onTitle(next)
          if (follows) {
            const derived = slugify(next)
            if (derived) onKey(derived)
          }
        }}
      />
      {isShown ? (
        <TextInput
          label={t("field.key")}
          hint={t(`field.keyHint.${kind}`)}
          monospace
          value={keyValue}
          errors={errors.key}
          onChange={(next) => {
            setIsOwn(true)
            onKey(next)
          }}
        />
      ) : (
        <p className="vqe-key">
          <span className="vqe-key__label" title={t("field.keyHint")}>
            {t("field.key")}
          </span>
          <code className="vqe-key__value">{keyValue || t("field.keyPending")}</code>
          <span className="vqe-key__note">
            {t(follows ? "field.keyFollows" : "field.keyFixed")}
          </span>
          <button type="button" className="vqe-key__edit" onClick={() => setIsEditing(true)}>
            {t("field.keyEdit")}
          </button>
        </p>
      )}
    </>
  )
}

function ConditionField({
  t,
  value,
  errors,
  onChange,
}: {
  t: Translate
  value: string
  errors?: string[]
  onChange: (value: string) => void
}) {
  return (
    <TextInput
      label={t("field.condition")}
      hint={t("field.conditionHint")}
      monospace
      placeholder={t("field.conditionPlaceholder")}
      value={value}
      errors={errors}
      onChange={onChange}
    />
  )
}

/**
 * How many columns one layer's grid has, per window size range.
 *
 * Drawn as the grid rather than typed as a number, and -- the part that used to
 * be missing -- shown even when there are no ranges yet, with the breakpoint it
 * needs offered right there. Hiding the field was why nobody could find it.
 */
function ColumnsField({
  t,
  label,
  hint,
  document,
  columns,
  inherited,
  path,
  errors,
  dispatch,
}: {
  t: Translate
  label: string
  hint: string
  document: QuestionnaireDefinition
  columns: Record<string, number>
  /** What this layer would take if it declared nothing, per range key. */
  inherited: (rangeKey: string) => number
  path: NodePath | null
  errors: Record<string, string[]>
  dispatch: (action: EditorAction) => void
}) {
  return (
    <fieldset className="vqe-fieldset vqe-fieldset--tight">
      <legend className="vqe-fieldset__legend">{label}</legend>
      <p className="vqe-form__hint">{hint}</p>
      {document.windowSizeRanges.length ? (
        <RangeStrips
          document={document}
          values={columns}
          errors={errors}
          extentOf={() => MAX_GRID_COLUMNS}
          label={(range) => t("columns.setFor", { range: range.label || range.key })}
          inheritedLabel={(range) => t("columns.inherited", { columns: inherited(range.key) })}
          onChange={(range, value) =>
            dispatch({ type: "setColumns", path, range, columns: value })
          }
        />
      ) : (
        <NoRanges
          t={t}
          onAddStandard={() => dispatch({ type: "addRanges", ranges: STANDARD_RANGES })}
          onAddOne={() => dispatch({ type: "insertRange" })}
        />
      )}
    </fieldset>
  )
}

/**
 * How wide a question is, per range: the cells it takes of its section's grid.
 *
 * The strip is drawn to the section's own resolved column count, so what is on
 * screen is the grid this question will actually land in -- pick six of twelve
 * on desktop and four of four on a phone, and the preview beside it moves.
 */
function MinimumColumnsField({
  t,
  document,
  question,
  path,
  errors,
  dispatch,
}: {
  t: Translate
  document: QuestionnaireDefinition
  question: QuestionDefinition
  path: QuestionPath
  errors: Record<string, string[]>
  dispatch: (action: EditorAction) => void
}) {
  const page = document.pages[path.page]
  const section = page?.sections[path.section]
  const grid = (rangeKey: string) =>
    columnsFor([document.columns, page?.columns, section?.columns], rangeKey)

  return (
    <fieldset className="vqe-fieldset vqe-fieldset--tight">
      <legend className="vqe-fieldset__legend">{t("question.minimumColumns")}</legend>
      <p className="vqe-form__hint">{t("question.minimumColumnsHint")}</p>
      {document.windowSizeRanges.length ? (
        <RangeStrips
          document={document}
          values={question.minimumColumns}
          errors={errors}
          extentOf={(range) => grid(range.key)}
          label={(range) => t("columns.spanFor", { range: range.label || range.key })}
          inheritedLabel={(range) => t("columns.inherited", { columns: grid(range.key) })}
          onChange={(range, columns) =>
            dispatch({ type: "setMinimumColumns", path, range, columns })
          }
        />
      ) : (
        <NoRanges
          t={t}
          onAddStandard={() => dispatch({ type: "addRanges", ranges: STANDARD_RANGES })}
          onAddOne={() => dispatch({ type: "insertRange" })}
        />
      )}
    </fieldset>
  )
}

/**
 * A named part of a form that can be shut.
 *
 * `details` rather than state of its own: the browser already knows how to be a
 * disclosure, including for a keyboard and a screen reader, and a group that
 * remembers whether it was open across a change of selection would put someone
 * back in a form that does not look like the one they left.
 */
function Group({
  title,
  gist,
  open,
  children,
}: {
  title: string
  /** What it says while it is shut, so the form can be skimmed closed. */
  gist?: string
  open?: boolean
  children: ReactNode
}) {
  return (
    <details className="vqe-group" open={open}>
      <summary className="vqe-group__summary">
        <span>{title}</span>
        {gist ? <span className="vqe-group__gist">{gist}</span> : null}
      </summary>
      <div className="vqe-group__body">{children}</div>
    </details>
  )
}

/**
 * Removing a row from a list.
 *
 * It says the word. It used to be a bare `×`, which is small, unlabelled to the
 * eye, sits next to the fields it destroys, and gives no clue what it takes
 * with it -- a poor thing to make the only irreversible control on the form.
 */
function RemoveButton({ title, onRemove }: { title: string; onRemove: () => void }) {
  const t = useStrings()
  return (
    <span className="vqe-item-controls">
      <Button variant="danger" title={title} onClick={onRemove}>
        {t("field.remove")}
      </Button>
    </span>
  )
}
