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
import { useStrings, type WithStrings } from "./strings.js"
import type { Translate } from "../strings.js"

/** The keys `newPage`, `newSection` and `newQuestion` hand out. */
const GENERATED_KEY = /^(page|section|question)(-\d+)?$/

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

      <KeyAndTitle
        t={t}
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
            info.supportsChoices ? "question.valueSetHintWithChoices" : "question.valueSetHint",
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

      <ConditionField
        t={t}
        value={question.condition}
        errors={errors.condition}
        onChange={(condition) => patch({ condition })}
      />

      <fieldset className="vqe-fieldset">
        <legend className="vqe-fieldset__legend">{t("question.layoutLegend")}</legend>
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
        <MinimumColumnsField
          t={t}
          document={document}
          question={question}
          path={path}
          errors={issuesAt(issues, `${base}.minimumColumns`)}
          dispatch={dispatch}
        />
      </fieldset>

      <fieldset className="vqe-fieldset">
        <legend className="vqe-fieldset__legend">{t("question.widgetLegend")}</legend>
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
      </fieldset>

      {info?.supportsChoices ? (
        <ChoiceList
          question={question}
          path={path}
          matrix={info.usesMatrixAxes}
          issues={issues}
          catalog={catalog}
          dispatch={dispatch}
          t={t}
        />
      ) : null}

      <ValidatorList
        question={question}
        path={path}
        issues={issues}
        catalog={catalog}
        dispatch={dispatch}
        t={t}
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
    <fieldset className="vqe-fieldset">
      <legend className="vqe-fieldset__legend">
        {t(matrix ? "choices.matrixLegend" : "choices.legend")}
      </legend>
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
  t,
}: Common & { question: QuestionDefinition; path: QuestionPath; t: Translate }) {
  const base = pathOf(path)
  const applicable = catalog ? validatorsFor(catalog, question.questionType) : []

  return (
    <fieldset className="vqe-fieldset">
      <legend className="vqe-fieldset__legend">{t("validators.legend")}</legend>
      <p className="vqe-form__hint">{t("validators.hint")}</p>
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
      <Button
        variant="quiet"
        onClick={() => dispatch({ type: "insertItem", path, list: "validators" })}
      >
        {t("validators.add")}
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
  t,
}: {
  handle: HandleProps
  t: Translate
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
        <DragHandle handle={handle} label={t("validators.item", { name: binding.validator })} />
        <Select
          label={t("validators.position", { position: index + 1 })}
          value={binding.validator}
          options={applicable.map((entry) => ({
            value: entry.key,
            label: entry.label,
          }))}
          errors={errors.validator}
          onChange={(validator) => patch({ validator, params: {}, messageOverrides: {} })}
        />
        <Checkbox
          label={t("validators.enabled")}
          checked={binding.isEnabled}
          onChange={(isEnabled) => patch({ isEnabled })}
        />
        <RemoveButton
          title={t("validators.remove")}
          onRemove={() => dispatch({ type: "removeItem", path, list: "validators", index })}
        />
      </div>

      {info ? (
        <>
          <p className="vqe-form__hint">
            {info.description}
            {info.clientMode === "server_only" ? (
              <strong> {t("validators.serverOnly")}</strong>
            ) : null}
            {info.clientMode === "custom" ? (
              <strong> {t("validators.customMode")}</strong>
            ) : null}
          </p>
          <SchemaForm
            label={t("validators.params")}
            schema={info.paramsSchema}
            value={binding.params}
            errors={errors.params}
            onChange={(params) => patch({ params })}
          />
          <fieldset className="vqe-fieldset vqe-fieldset--tight">
            <legend className="vqe-fieldset__legend">{t("validators.messages")}</legend>
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
  t,
  keyValue,
  title,
  errors,
  onKey,
  onTitle,
}: {
  t: Translate
  keyValue: string
  title: string
  errors: Record<string, string[]>
  onKey: (key: string) => void
  onTitle: (title: string) => void
}) {
  return (
    <div className="vqe-row">
      <TextInput
        label={t("field.title")}
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
        label={t("field.key")}
        hint={t("field.keyHint")}
        monospace
        value={keyValue}
        errors={errors.key}
        onChange={onKey}
      />
    </div>
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

function ColumnsField({
  t,
  label,
  hint,
  document,
  columns,
  path,
  errors,
  dispatch,
}: {
  t: Translate
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
            placeholder={t("field.columns.inherit")}
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
  if (!document.windowSizeRanges.length) return null
  return (
    <fieldset className="vqe-fieldset vqe-fieldset--tight">
      <legend className="vqe-fieldset__legend">{t("question.minimumColumns")}</legend>
      <p className="vqe-form__hint">{t("question.minimumColumnsHint")}</p>
      <div className="vqe-row">
        {document.windowSizeRanges.map((range) => (
          <NumberInput
            key={range.key}
            label={range.label || range.key}
            min={1}
            placeholder={t("question.minimumColumnsPlaceholder")}
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

function RemoveButton({ title, onRemove }: { title: string; onRemove: () => void }) {
  return (
    <span className="vqe-item-controls">
      <button type="button" title={title} onClick={onRemove}>
        ×
      </button>
    </span>
  )
}
