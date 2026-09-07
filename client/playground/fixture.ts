/**
 * A questionnaire to poke at, and a server that pretends to hold it.
 *
 * The fixture is deliberately awkward rather than tidy: spans that do not
 * divide evenly into the grid, a question pinned to the start of its row, an
 * "other" escape hatch, a matrix, a collapsed section, a skippable page, a
 * required field and a validator with params. A playground that only holds
 * simple cases is a playground that only proves the simple cases.
 *
 * Nothing here is imported by the package. It exists so the editor and the
 * renderer can be driven without a Django instance behind them.
 */

import type {
  EditorCatalog,
  QuestionDefinition,
  QuestionnaireDefinition,
} from "../src/definition.js"

// ------------------------------------------------------------------- catalog

/** Spread over every question type entry, so each one only names its own bits. */
const TYPE_DEFAULTS = {
  answerShape: "scalar",
  supportsChoices: false,
  supportsValueSet: false,
  supportsOtherOption: false,
  usesMatrixAxes: false,
  requiresItemType: false,
  requiresSubQuestionnaire: false,
}

const QUESTION_TYPES: [key: string, label: string, extra?: Record<string, unknown>][] = [
  ["free_text", "Free text"],
  ["url", "URL"],
  ["number", "Number"],
  ["year", "Year"],
  ["date", "Date"],
  ["date_time", "Date and time"],
  ["month", "Month"],
  ["time", "Time"],
  ["single_choice", "Single choice", { supportsChoices: true, supportsOtherOption: true }],
  [
    "multiple_choice",
    "Multiple choice",
    { answerShape: "list", supportsChoices: true, supportsOtherOption: true },
  ],
  ["single_select", "Single select from a value set", { supportsValueSet: true }],
  [
    "multi_select",
    "Multi select from a value set",
    { answerShape: "list", supportsValueSet: true },
  ],
  ["number_range", "Number range", { answerShape: "range" }],
  ["date_range", "Date range", { answerShape: "range" }],
  ["date_time_range", "Date and time range", { answerShape: "range" }],
  ["single_file", "Single file", { answerShape: "file" }],
  ["multiple_files", "Multiple files", { answerShape: "file_list" }],
  [
    "binary_matrix",
    "Binary matrix of selections",
    { answerShape: "matrix", supportsChoices: true, usesMatrixAxes: true },
  ],
  ["item_list", "List of items", { answerShape: "list", requiresItemType: true }],
]

/** Mirrors what `install_default_widgets` creates, so the keys line up. */
const WIDGETS: [
  key: string,
  name: string,
  types: string[],
  defaults: string[],
  props?: Record<string, unknown>,
  defaultProps?: Record<string, unknown>,
][] = [
  [
    "input",
    "Text field",
    ["free_text", "url"],
    ["free_text", "url"],
    { placeholder: { type: "string", title: "Placeholder" } },
  ],
  [
    "textarea",
    "Text area",
    ["free_text"],
    [],
    { rows: { type: "integer", title: "Rows", minimum: 2, maximum: 20 } },
    { rows: 4 },
  ],
  [
    "number-input",
    "Number field",
    ["number", "year"],
    ["number", "year"],
    { prefix: { type: "string", title: "Prefix" }, step: { type: "number", title: "Step" } },
  ],
  [
    "radio-group",
    "Radio group",
    ["single_choice"],
    ["single_choice"],
    { orientation: { enum: ["vertical", "horizontal"], title: "Orientation" } },
    { orientation: "vertical" },
  ],
  [
    "checkbox-group",
    "Checkbox group",
    ["multiple_choice"],
    ["multiple_choice"],
    { columns: { type: "integer", title: "Columns", minimum: 1, maximum: 4 } },
    { columns: 1 },
  ],
  ["select", "Dropdown", ["single_select", "single_choice"], ["single_select"]],
  ["multi-select", "Multiple dropdown", ["multi_select", "multiple_choice"], ["multi_select"]],
  ["date-input", "Date field", ["date", "date_time", "month"], ["date", "date_time", "month"]],
  ["time-input", "Time field", ["time"], ["time"]],
  [
    "date-range",
    "Date range",
    ["date_range", "date_time_range"],
    ["date_range", "date_time_range"],
    {
      startLabel: { type: "string", title: "Start label" },
      endLabel: { type: "string", title: "End label" },
    },
    { startLabel: "From", endLabel: "Until" },
  ],
  ["number-range", "Number range", ["number_range"], ["number_range"]],
  [
    "file-upload",
    "File field",
    ["single_file", "multiple_files"],
    ["single_file", "multiple_files"],
    { accept: { type: "string", title: "Accept" } },
  ],
  ["matrix", "Matrix", ["binary_matrix"], ["binary_matrix"]],
  [
    "item-list",
    "List of items",
    ["item_list"],
    ["item_list"],
    { addLabel: { type: "string", title: "Add label" } },
  ],
]

export const catalog: EditorCatalog = {
  catalogVersion: 1,
  defaultColumnCount: 12,
  questionTypes: QUESTION_TYPES.map(([key, label, extra]) => ({
    ...TYPE_DEFAULTS,
    key,
    label,
    ...extra,
  })),
  scalarQuestionTypes: ["free_text", "url", "number", "year", "date", "month", "time"],
  validators: [
    {
      key: "required",
      label: "Required",
      description: "The answer may not be empty.",
      paramsSchema: { type: "object", properties: {} },
      errorKeys: [{ key: "required", message: "This is required." }],
      questionTypes: null,
      clientMode: "checks",
      skipWhenEmpty: false,
      readsContext: false,
    },
    {
      key: "min_length",
      label: "Minimum length",
      description: "At least this many characters.",
      paramsSchema: {
        type: "object",
        properties: { minimum: { type: "integer", title: "Minimum" } },
        required: ["minimum"],
      },
      errorKeys: [{ key: "too_short", message: "Use at least {minimum} characters." }],
      questionTypes: ["free_text"],
      clientMode: "checks",
      skipWhenEmpty: true,
      readsContext: false,
    },
    {
      key: "email",
      label: "Email address",
      description: "Must look like an email address.",
      paramsSchema: { type: "object", properties: {} },
      errorKeys: [{ key: "invalid", message: "That is not an email address." }],
      questionTypes: ["free_text"],
      clientMode: "checks",
      skipWhenEmpty: true,
      readsContext: false,
    },
    {
      key: "credit_check",
      label: "Credit check",
      description: "Asks a third party, so only the server can run it.",
      paramsSchema: { type: "object", properties: {} },
      errorKeys: [{ key: "refused", message: "That did not pass." }],
      questionTypes: null,
      clientMode: "server_only",
      skipWhenEmpty: true,
      readsContext: false,
    },
  ],
  widgets: WIDGETS.map(
    ([key, name, questionTypes, defaultForQuestionTypes, props, defaults]) => ({
      key,
      name,
      description: "",
      component: key,
      propsSchema: { type: "object", properties: props ?? {}, additionalProperties: false },
      defaultProps: defaults ?? {},
      questionTypes,
      defaultForQuestionTypes,
    }),
  ),
  valueSets: [
    {
      key: "countries",
      name: "Countries",
      description: "ISO 3166-1.",
      source: "static",
      resolvedByTheClient: false,
    },
  ],
  questionnaires: [
    {
      key: "intake",
      name: "Client intake",
      versions: [{ version: 2, title: "Client intake", status: "draft" }],
    },
  ],
  choiceAxes: [
    { value: "option", label: "Option" },
    { value: "row", label: "Row" },
    { value: "column", label: "Column" },
  ],
  sectionStates: [
    { value: "open", label: "Open" },
    { value: "closed", label: "Collapsed" },
  ],
  versionStatuses: [
    { value: "draft", label: "Draft" },
    { value: "published", label: "Published" },
    { value: "retired", label: "Retired" },
  ],
  editPolicies: [
    { value: "always", label: "Always" },
    { value: "until_submitted", label: "Until submitted" },
    { value: "never", label: "Never" },
  ],
}

// ------------------------------------------------------------------ document

function question(over: Partial<QuestionDefinition> & { key: string }): QuestionDefinition {
  return {
    title: "",
    description: "",
    questionType: "free_text",
    itemQuestionType: "",
    condition: "",
    requiresBeingFirstInARow: false,
    requiresBeingLastInARow: false,
    minimumColumns: {},
    widget: null,
    widgetProps: {},
    allowsOther: false,
    otherLabel: "",
    valueSet: null,
    subQuestionnaire: null,
    subQuestionnaireVersion: null,
    choices: [],
    validators: [],
    ...over,
  }
}

/** Half a row on desktop, a whole one on a phone -- the commonest shape. */
const HALF = { mobile: 4, tablet: 8, desktop: 6 }
const FULL = { mobile: 4, tablet: 8, desktop: 12 }

export const document: QuestionnaireDefinition = {
  documentVersion: 1,
  questionnaire: { key: "intake", name: "Client intake" },
  version: 2,
  title: "Client intake",
  description: "What we need before the first call.",
  status: "draft",
  editPolicy: "always",
  responsesDueAt: null,
  editsDueAt: null,
  windowSizeRanges: [
    { key: "mobile", label: "Phone", minWidth: 0, maxWidth: 767 },
    { key: "tablet", label: "Tablet", minWidth: 768, maxWidth: 1023 },
    { key: "desktop", label: "Desktop", minWidth: 1024, maxWidth: null },
  ],
  columns: { mobile: 4, tablet: 8, desktop: 12 },
  state: {
    responseCount: 0,
    requiresAcknowledgement: false,
    isPublished: false,
    fingerprint: "f1e2d3c4b5a6",
  },
  pages: [
    {
      key: "about",
      title: "About you",
      description: "The basics, so we know who we are talking to.",
      conclusion: "",
      condition: "",
      isSkippable: false,
      columns: {},
      sections: [
        {
          key: "identity",
          title: "Who you are",
          description: "",
          conclusion: "",
          defaultState: "open",
          condition: "",
          columns: {},
          questions: [
            question({
              key: "first-name",
              title: "First name",
              minimumColumns: HALF,
              validators: [
                { validator: "required", params: {}, messageOverrides: {}, isEnabled: true },
              ],
            }),
            question({
              key: "last-name",
              title: "Last name",
              minimumColumns: HALF,
              validators: [
                { validator: "required", params: {}, messageOverrides: {}, isEnabled: true },
              ],
            }),
            question({
              key: "email",
              title: "Email",
              minimumColumns: { mobile: 4, tablet: 5, desktop: 7 },
              widgetProps: { placeholder: "you@example.com" },
              validators: [
                { validator: "required", params: {}, messageOverrides: {}, isEnabled: true },
                { validator: "email", params: {}, messageOverrides: {}, isEnabled: true },
              ],
            }),
            question({
              key: "team-size",
              // A five-column question after a seven-column one: the row fills
              // exactly, which is the case an even grid never exercises.
              title: "How big is the team?",
              questionType: "number",
              minimumColumns: { mobile: 4, tablet: 3, desktop: 5 },
              widgetProps: { prefix: "~" },
            }),
            question({
              key: "role",
              title: "What is your role?",
              questionType: "single_choice",
              allowsOther: true,
              otherLabel: "Something else",
              minimumColumns: { mobile: 4, tablet: 8, desktop: 5 },
              choices: [
                {
                  axis: "option",
                  value: "eng",
                  label: "Engineering",
                  extra: {},
                  isActive: true,
                },
                { axis: "option", value: "design", label: "Design", extra: {}, isActive: true },
                {
                  axis: "option",
                  value: "ops",
                  label: "Operations",
                  extra: {},
                  isActive: true,
                },
                {
                  axis: "option",
                  value: "legacy",
                  label: "Retired option",
                  extra: {},
                  isActive: false,
                },
              ],
            }),
            question({
              key: "stack",
              title: "What do you work with?",
              questionType: "multiple_choice",
              minimumColumns: { mobile: 4, tablet: 8, desktop: 7 },
              widgetProps: { columns: 2 },
              choices: [
                { axis: "option", value: "py", label: "Python", extra: {}, isActive: true },
                { axis: "option", value: "ts", label: "TypeScript", extra: {}, isActive: true },
                { axis: "option", value: "go", label: "Go", extra: {}, isActive: true },
                { axis: "option", value: "rb", label: "Ruby", extra: {}, isActive: true },
              ],
            }),
            question({
              key: "notes",
              title: "Anything else we should know?",
              description: "Free form. Markdown is fine.",
              widget: "textarea",
              widgetProps: { rows: 5 },
              minimumColumns: FULL,
              // Pinned, so it opens a row even when the one above has slack.
              requiresBeingFirstInARow: true,
              validators: [
                {
                  validator: "min_length",
                  params: { minimum: 20 },
                  messageOverrides: {},
                  isEnabled: true,
                },
              ],
            }),
          ],
        },
        {
          key: "scheduling",
          title: "When we can talk",
          description: "This section declares six columns of its own on desktop.",
          conclusion: "",
          defaultState: "open",
          condition: "",
          // A layer that overrides its parent, so the inheritance is visible.
          columns: { desktop: 6 },
          questions: [
            question({
              key: "window",
              title: "Which weeks work?",
              questionType: "date_range",
              minimumColumns: { mobile: 4, tablet: 8, desktop: 6 },
            }),
            question({
              key: "availability",
              title: "Availability",
              questionType: "binary_matrix",
              minimumColumns: { mobile: 4, tablet: 8, desktop: 6 },
              choices: [
                { axis: "row", value: "mon", label: "Monday", extra: {}, isActive: true },
                { axis: "row", value: "tue", label: "Tuesday", extra: {}, isActive: true },
                { axis: "row", value: "wed", label: "Wednesday", extra: {}, isActive: true },
                { axis: "column", value: "am", label: "Morning", extra: {}, isActive: true },
                { axis: "column", value: "pm", label: "Afternoon", extra: {}, isActive: true },
              ],
            }),
          ],
        },
      ],
    },
    {
      key: "project",
      title: "The project",
      description: "",
      conclusion: "Thanks -- we will read this before the call.",
      condition: "",
      isSkippable: true,
      columns: {},
      sections: [
        {
          key: "scope",
          title: "Scope",
          description: "",
          conclusion: "",
          defaultState: "open",
          condition: "",
          columns: {},
          questions: [
            question({
              key: "goals",
              title: "What are you trying to do?",
              widget: "textarea",
              minimumColumns: FULL,
            }),
            question({
              key: "links",
              title: "Anything to read?",
              questionType: "item_list",
              itemQuestionType: "url",
              minimumColumns: { mobile: 4, tablet: 8, desktop: 6 },
              widgetProps: { addLabel: "Add a link" },
            }),
            question({
              key: "brief",
              title: "Upload a brief",
              questionType: "single_file",
              minimumColumns: { mobile: 4, tablet: 4, desktop: 6 },
              widgetProps: { accept: ".pdf,.md" },
            }),
          ],
        },
        {
          key: "budget",
          title: "Budget",
          description: "Starts collapsed, and only appears once there is a goal.",
          conclusion: "",
          defaultState: "closed",
          condition: "goals",
          columns: {},
          questions: [
            question({
              key: "range",
              title: "Roughly what range?",
              questionType: "number_range",
              minimumColumns: { mobile: 4, tablet: 8, desktop: 6 },
            }),
            question({
              key: "approval",
              title: "Who signs it off?",
              minimumColumns: { mobile: 4, tablet: 8, desktop: 6 },
              validators: [
                {
                  validator: "credit_check",
                  params: {},
                  messageOverrides: {},
                  isEnabled: true,
                },
              ],
            }),
          ],
        },
      ],
    },
  ],
}

// ------------------------------------------------------------------- the api

/** Long enough to see the loading state, short enough not to be annoying. */
const LATENCY = 120

function later<T>(value: T): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(structuredClone(value)), LATENCY))
}

/**
 * An `EditorApi` over a variable.
 *
 * It accepts every save, so the playground is for the interface rather than for
 * the server's rules -- what a real one refuses is covered by the Python tests.
 * Saving does round-trip, though, so `unsaved` clears and Revert has something
 * to go back to.
 */
export function fakeApi(onSave?: (document: QuestionnaireDefinition) => void) {
  let stored = structuredClone(document)
  return {
    fetchCatalog: () => later(catalog),
    fetchDefinition: () => later(stored),
    saveDefinition: (
      _questionnaire: string,
      _version: number,
      sent: QuestionnaireDefinition,
    ) => {
      stored = { ...structuredClone(sent), state: document.state }
      onSave?.(stored)
      return later(stored)
    },
    forkVersion: () => later({ ...stored, version: stored.version + 1, status: "draft" }),
    listQuestionnaires: () => later([]),
    createQuestionnaire: () => later(stored),
    deleteQuestionnaire: () => later(undefined),
    deleteVersion: () => later(undefined),
    fetchResponses: () => later({ columns: [], rows: [], count: 0 }),
  }
}
