/**
 * The authoring wire format, as emitted by `vinta_django_questionnaires.definition`.
 *
 * The plan in `plan.ts` is what a respondent's browser renders; this is what an
 * author edits. They are deliberately different shapes: the plan is resolved
 * and flattened, this one keeps every field as its author set it -- empty where
 * they left the default -- because that is what has to go back.
 *
 * Keys are identity. The server matches a page, section, question or choice to
 * what it has stored by key, so changing a key is a delete and a create, not a
 * rename.
 */

/** The document version this editor was written against. */
export const SUPPORTED_DOCUMENT_VERSION = 1

/** The catalog version this editor was written against. */
export const SUPPORTED_CATALOG_VERSION = 1

export type ChoiceAxis = "option" | "row" | "column"

export interface ChoiceDefinition {
  axis: ChoiceAxis
  value: string
  label: string
  extra: Record<string, unknown>
  isActive: boolean
}

export interface ValidatorDefinition {
  validator: string
  params: Record<string, unknown>
  messageOverrides: Record<string, string>
  isEnabled: boolean
}

export interface QuestionDefinition {
  key: string
  title: string
  description: string
  questionType: string
  itemQuestionType: string
  condition: string
  requiresBeingFirstInARow: boolean
  requiresBeingLastInARow: boolean
  /** Per window size range key. A range left out takes the default. */
  minimumColumns: Record<string, number>
  /** The widget the author chose, or `null` for the question type's default. */
  widget: string | null
  widgetProps: Record<string, unknown>
  allowsOther: boolean
  otherLabel: string
  valueSet: string | null
  subQuestionnaire: string | null
  subQuestionnaireVersion: number | null
  choices: ChoiceDefinition[]
  validators: ValidatorDefinition[]
  /** Written by the server, ignored on the way back. */
  resolved?: { widget: string | null; fingerprint: string }
}

export interface SectionDefinition {
  key: string
  title: string
  description: string
  conclusion: string
  defaultState: "open" | "closed"
  condition: string
  /** The columns this section declares itself, not the ones it inherits. */
  columns: Record<string, number>
  questions: QuestionDefinition[]
}

export interface PageDefinition {
  key: string
  title: string
  description: string
  conclusion: string
  condition: string
  isSkippable: boolean
  columns: Record<string, number>
  sections: SectionDefinition[]
}

export interface WindowSizeRangeDefinition {
  key: string
  label: string
  minWidth: number
  maxWidth: number | null
}

export interface QuestionnaireDefinition {
  documentVersion: number
  questionnaire: { key: string; name: string }
  version: number
  title: string
  description: string
  status: string
  editPolicy: string
  responsesDueAt: string | null
  editsDueAt: string | null
  windowSizeRanges: WindowSizeRangeDefinition[]
  columns: Record<string, number>
  pages: PageDefinition[]
  /** Written by the server, ignored on the way back. */
  state?: {
    responseCount: number
    requiresAcknowledgement: boolean
    isPublished: boolean
    fingerprint: string
  }
}

// ------------------------------------------------------------------ catalog

export interface QuestionTypeInfo {
  key: string
  label: string
  answerShape: string
  supportsChoices: boolean
  supportsValueSet: boolean
  supportsOtherOption: boolean
  usesMatrixAxes: boolean
  requiresItemType: boolean
  requiresSubQuestionnaire: boolean
}

export interface ValidatorInfo {
  key: string
  label: string
  description: string
  /** JSON Schema for what this validator's `params` may hold. */
  paramsSchema: Record<string, unknown>
  errorKeys: { key: string; message: string }[]
  /** `null` means it applies to every question type. */
  questionTypes: string[] | null
  clientMode: "checks" | "custom" | "server_only"
  skipWhenEmpty: boolean
  readsContext: boolean
}

export interface WidgetInfo {
  key: string
  name: string
  description: string
  component: string
  propsSchema: Record<string, unknown>
  defaultProps: Record<string, unknown>
  questionTypes: string[]
  defaultForQuestionTypes: string[]
}

export interface ValueSetInfo {
  key: string
  name: string
  description: string
  source: string
  resolvedByTheClient: boolean
}

export interface QuestionnaireInfo {
  key: string
  name: string
  versions: { version: number; title: string; status: string }[]
}

export interface Labelled {
  value: string
  label: string
}

export interface EditorCatalog {
  catalogVersion: number
  defaultColumnCount: number
  questionTypes: QuestionTypeInfo[]
  scalarQuestionTypes: string[]
  validators: ValidatorInfo[]
  widgets: WidgetInfo[]
  valueSets: ValueSetInfo[]
  questionnaires: QuestionnaireInfo[]
  choiceAxes: Labelled[]
  sectionStates: Labelled[]
  versionStatuses: Labelled[]
  editPolicies: Labelled[]
}

// ------------------------------------------------------------------- issues

/**
 * One node the server -- or the editor's own checks -- would not accept.
 *
 * `path` addresses a node the way the editor's state does:
 * `pages.0.sections.1.questions.2`, or `""` for the version itself.
 */
export interface DefinitionIssue {
  path: string
  errors: Record<string, string[]>
}

/** Where a non-field error is reported, matching Django's own key. */
export const NON_FIELD = "__all__"

// ---------------------------------------------------------------- accessors

export function questionTypeInfo(
  catalog: EditorCatalog,
  questionType: string,
): QuestionTypeInfo | undefined {
  return catalog.questionTypes.find((entry) => entry.key === questionType)
}

export function validatorInfo(catalog: EditorCatalog, key: string): ValidatorInfo | undefined {
  return catalog.validators.find((entry) => entry.key === key)
}

/** The validators that may be attached to a question of *questionType*. */
export function validatorsFor(catalog: EditorCatalog, questionType: string): ValidatorInfo[] {
  return catalog.validators.filter(
    (entry) => entry.questionTypes === null || entry.questionTypes.includes(questionType),
  )
}

/** The widgets that can render a question of *questionType*. */
export function widgetsFor(catalog: EditorCatalog, questionType: string): WidgetInfo[] {
  return catalog.widgets.filter((widget) => widget.questionTypes.includes(questionType))
}

/** The widget used when a question of *questionType* names none. */
export function defaultWidgetFor(
  catalog: EditorCatalog,
  questionType: string,
): WidgetInfo | undefined {
  return catalog.widgets.find((widget) => widget.defaultForQuestionTypes.includes(questionType))
}
