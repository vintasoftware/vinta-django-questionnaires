/**
 * Every word the client says, in one place.
 *
 * The package carries no i18n dependency and no locale files: a host project
 * translates it by handing over a catalogue of its own, and anything it leaves
 * out falls back to the English below.  That keeps the editor translatable
 * without deciding for the host which i18n library it has to adopt.
 *
 * ```tsx
 * <QuestionnaireEditor strings={{ "editor.save": "Salvar" }} ... />
 * ```
 *
 * Most entries are a plain string, because most sentences stand on their own.
 * The twenty-odd that do not are functions, taking what the editor only knows
 * as it renders:
 *
 * ```ts
 * "editor.issues.heading": ({ count }) => `${count} coisas a corrigir:`
 * ```
 *
 * There is no template syntax between the two -- no placeholder to spell
 * right, nothing substituted at run time -- and no need to remember which key
 * is which, because the type says so.  The compiler asks for a string where a
 * key is a string, for a function where it is a function, and for exactly that
 * function's parameters, by name and with their real types.
 *
 * The functions are also what lets a host use the i18n library it already has.
 * Their parameters are only known as the editor renders, so a finished string
 * could never reach a `t()` carrying them; a function can, and hands the whole
 * sentence -- interpolation, plurals, gender -- to whatever the project uses:
 *
 * ```tsx
 * strings={{
 *   "editor.save": t("questionnaire.save"),
 *   "editor.issues.heading": ({ count }) => t("questionnaire.issues", { count }),
 * }}
 * ```
 *
 * What is *not* here: the messages a respondent sees when an answer fails
 * validation.  Those are templates the server sends down in the plan, so
 * Django's own translation framework covers them, and `formatMessage` fills
 * them in to the letter of what Python does.  Nor are diagnostics and thrown
 * `Error`s, which go to consoles and error trackers where a stable English
 * string is worth more than a translated one.
 */

export const defaultStrings = {
  // ------------------------------------------------------------ the editor
  "editor.loading": "Loading the questionnaire...",
  "editor.retry": "Try again",
  "editor.revert": "Revert",
  "editor.fork": "Fork into a new draft",
  "editor.save": "Save",
  "editor.saving": "Saving...",
  "editor.badge.unsaved": "unsaved",
  "editor.missing": "That is gone. Pick something from the outline.",
  "editor.issues.heading": ({ count }: { count: number }) =>
    `${count} thing(s) need fixing before this can be saved:`,
  "editor.orphaned": ({ keys }: { keys: string }) =>
    `These question keys are gone since the last save, so the answers stored against them will no longer be read: ${keys}`,
  "editor.acknowledge.notice": ({ count }: { count: number }) =>
    `This version already has ${count} response(s). Changing what a question asks changes what those answers mean. The ordinary way to make a change like this is to fork a new draft; editing in place is allowed, and recorded.`,
  "editor.acknowledge.understood":
    "I understand what this edit does to the responses already given.",
  "editor.acknowledge.reason": "Reason",
  "editor.acknowledge.reasonHint": "Kept with the record of the edit.",

  // The titles a newly inserted node is given until it is named.
  "editor.new.page": "Untitled page",
  "editor.new.section": "Untitled section",
  "editor.new.question": "Untitled question",

  // ----------------------------------------------------------- the outline
  "outline.label": "Questionnaire outline",
  "outline.untitled": "Untitled",
  "outline.untitled.page": "untitled page",
  "outline.untitled.section": "untitled section",
  "outline.untitled.question": "untitled question",
  "outline.flag": "Has a problem",
  "outline.badge.skippable": "skippable",
  "outline.badge.conditional": "conditional",
  "outline.add.page": "+ Page",
  "outline.add.section": "+ Section",
  "outline.add.question": "+ Question",
  "outline.list.pages": "pages",
  "outline.list.sections": "sections",
  "outline.list.questions": "questions",
  // What a row is called when it is picked up or deleted.
  "outline.item.page": ({ label }: { label: string }) => `page ${label}`,
  "outline.item.section": ({ label }: { label: string }) => `section ${label}`,
  "outline.item.question": ({ label }: { label: string }) => `question ${label}`,
  "outline.delete.page": "Delete this page",
  "outline.delete.section": "Delete this section",
  "outline.delete.question": "Delete this question",

  // ------------------------------------------------- dragging to reorder
  "sortable.reorder": ({ name }: { name: string }) => `Reorder ${name}`,
  "sortable.dragToReorder": ({ name }: { name: string }) => `Drag to reorder ${name}`,
  "sortable.pickedUp": ({ name, list }: { name: string; list: string }) =>
    `Picked up ${name} in ${list}. Use the arrow keys to move it, space to drop it.`,
  "sortable.dropped": ({ name }: { name: string }) => `Dropped ${name}.`,
  "sortable.cancelled": ({ name }: { name: string }) => `Left ${name} where it was.`,

  // ------------------------------------------------------- shared fields
  "field.empty": "--",
  "field.title": "Title",
  "field.key": "Key",
  "field.keyHint":
    "Answers are stored against this. Changing it orphans the answers already given.",
  "field.label": "Label",
  "field.description": "Description",
  "field.conclusion": "Conclusion",
  "field.markdownHint": "Markdown.",
  "field.remove": "Remove",
  "field.condition": "Condition",
  "field.conditionHint": "A JMESPath expression over the answers so far. Empty always applies.",
  "field.conditionPlaceholder": "e.g. has_company",
  "field.columns.inherit": "inherit",

  // ---------------------------------------------------------- the version
  "version.responses": ({ count }: { count: number }) =>
    `${count} response(s) have already been given against this version.`,
  "version.noResponses": "No responses yet, so this version can still be changed freely.",
  "version.status": "Status",
  "version.editPolicy": "Edit policy",
  "version.editPolicyHint": "Whether a respondent may come back and change what they answered.",
  "version.responsesDueAt": "Responses due at",
  "version.dueAtHint": "ISO 8601, e.g. 2026-12-31T23:59:00Z. Empty for no deadline.",
  "version.editsDueAt": "Edits due at",
  "version.columns": "Columns of the questionnaire's grid",
  "version.columnsHint": "What every page inherits unless it says otherwise.",

  // --------------------------------------------------- window size ranges
  "ranges.legend": "Window size ranges",
  "ranges.hint":
    "The breakpoints this questionnaire is laid out against. Every column count below is keyed by one of them.",
  "ranges.from": "From (px)",
  "ranges.to": "To (px)",
  "ranges.unbounded": "unbounded",
  "ranges.add": "+ Window size range",

  // ------------------------------------------------------------- the page
  "page.heading": "Page",
  "page.descriptionHint": "Markdown, shown at the top of the page.",
  "page.conclusionHint": "Markdown, shown once the page is filled in.",
  "page.skippable": "Skippable",
  "page.skippableHint": "Whether the respondent may leave this page for later and move on.",
  "page.columns": "Columns of this page's grid",
  "page.columnsHint": "Empty inherits from the questionnaire.",

  // ---------------------------------------------------------- the section
  "section.heading": "Section",
  "section.defaultState": "Default state",
  "section.defaultStateHint": "Whether the section starts open or collapsed.",
  "section.columns": "Columns of this section's grid",
  "section.columnsHint": "Empty inherits from the page.",

  // --------------------------------------------------------- the question
  "question.heading": "Question",
  "question.fingerprint": ({ fingerprint }: { fingerprint: string }) =>
    `Fingerprint ${fingerprint} -- answers from another version pool with this question while it stays the same.`,
  "question.type": "Question type",
  "question.itemType": "Item type",
  "question.itemTypeHint": "The type of each entry of the list.",
  "question.subQuestionnaire": "Sub-questionnaire",
  "question.pinnedVersion": "Pinned version",
  "question.pinnedVersionHint": "Empty follows whichever version of it is published.",
  "question.latestPublished": "Latest published",
  "question.versionOption": ({
    version,
    title,
    status,
  }: {
    version: number
    title: string
    status: string
  }) => `v${version} -- ${title} (${status})`,
  "question.valueSet": "Value set",
  "question.valueSetHint": "Where the options come from.",
  "question.valueSetHintWithChoices":
    "Where the options come from, instead of the inline choices below.",
  "question.allowsOther": "Allows an other option",
  "question.allowsOtherHint": "Adds a free text escape hatch to the choices.",
  "question.otherLabel": "Other label",
  "question.layoutLegend": "Layout",
  "question.firstInRow": "Must be first in its row",
  "question.lastInRow": "Must be last in its row",
  "question.minimumColumns": "Minimum columns",
  "question.minimumColumnsHint":
    "The narrowest this question may be rendered in each range. Empty takes the default.",
  "question.minimumColumnsPlaceholder": "default",
  "question.widgetLegend": "Widget",
  "question.widget": "Widget",
  "question.widgetHint": "The component the client renders this with.",
  "question.widgetDefaultHint": "Empty uses the type's default.",
  "question.widgetDefaultNamedHint": ({ name }: { name: string }) =>
    `Empty uses the type's default, which is ${name}.`,
  "question.widgetEmpty": "Default for the type",
  "question.widgetProps": "Widget props",

  // ---------------------------------------------------------- the choices
  "choices.legend": "Choices",
  "choices.matrixLegend": "Rows and columns",
  "choices.listName": "choices",
  "choices.blank": "a blank choice",
  "choices.item": ({ name }: { name: string }) => `choice ${name}`,
  "choices.axis": "Axis",
  "choices.value": "Value",
  "choices.valueHint": "What is stored in the answer.",
  "choices.active": "Active",
  "choices.remove": "Remove this choice",
  "choices.add": "+ Choice",

  // ------------------------------------------------------- the validators
  "validators.legend": "Validators",
  "validators.hint":
    "They run in this order, and each one sees what the ones before it recorded.",
  "validators.listName": "validators",
  "validators.item": ({ name }: { name: string }) => `validator ${name}`,
  "validators.position": ({ position }: { position: number }) => `${position}.`,
  "validators.enabled": "Enabled",
  "validators.remove": "Remove this validator",
  "validators.serverOnly": "Checked on submit only -- the browser cannot run it.",
  "validators.customMode":
    "Needs an implementation registered under the same key in the browser.",
  "validators.params": "Params",
  "validators.messages": "Messages",
  "validators.add": "+ Validator",

  // ------------------------------------------- a schema rendered as a form
  "schemaForm.required": ({ label }: { label: string }) => `${label} *`,
  "schemaForm.jsonOnly": "This one declares no properties, so it is edited as JSON.",
  "schemaForm.jsonHint": "JSON.",
  "schemaForm.invalidJson": "This is not valid JSON.",

  // ---------------------------- what the editor can tell without the server
  "issue.summary": ({ path, message }: { path: string; message: string }) =>
    `${path}: ${message}`,
  "issue.summary.field": ({
    path,
    field,
    message,
  }: {
    path: string
    field: string
    message: string
  }) => `${path} ${field}: ${message}`,
  "issue.summary.root": "questionnaire",
  "issue.key.required": "A key is required -- answers are stored against it.",
  "issue.key.invalid": "A key may hold letters, digits, hyphens and underscores only.",
  "issue.page.duplicateKey": "Another page already uses this key.",
  "issue.page.title": "A page needs a title.",
  "issue.section.duplicateKey": "Another section of this page already uses this key.",
  "issue.section.title": "A section needs a title.",
  "issue.question.duplicateKey": "Another question of this version already uses this key.",
  "issue.question.title": "A question needs a title.",
  "issue.questionType.missing": "Pick a question type.",
  "issue.itemType.required": "A list of items needs the type of its items.",
  "issue.itemType.unsupported": "Only a list of items takes an item type.",
  "issue.subQuestionnaire.required": "This question type needs a sub-questionnaire.",
  "issue.subQuestionnaire.unsupported": "Only a sub-questionnaire question nests another one.",
  "issue.valueSet.required": "This question type needs a value set.",
  "issue.valueSet.unsupported": "This question type does not take a value set.",
  "issue.allowsOther.unsupported": "This question type does not take an other option.",
  "issue.choices.unsupported": "This question type does not take choices.",
  "issue.validator.unknown": "There is no validator with this key.",
  "issue.validator.inapplicable": ({ label }: { label: string }) =>
    `${label} does not apply to this question type.`,
  "issue.choice.valueRequired": "A choice needs a value -- it is what is stored.",
  "issue.choice.duplicateValue": "Another choice already uses this value.",
} satisfies Record<string, StringValue>

/** A message that needs something filled in: what it needs in, sentence out. */
export type StringFunction = (...params: never[]) => string

/**
 * A value in the catalogue.
 *
 * A plain string where the sentence stands on its own, which is most of them,
 * and a function where it needs something the editor only knows as it renders.
 * Which one a key is is not something to remember: it is in the type, so the
 * compiler asks for whichever the key actually is.
 */
export type StringValue = string | StringFunction

/** A complete catalogue: what the components are actually handed. */
export type QuestionnaireStrings = typeof defaultStrings

/** Every key the client looks up. */
export type StringKey = keyof QuestionnaireStrings

/** What *key* has to be given: nothing at all, or its function's parameters. */
export type ParamsOf<Key extends StringKey> = QuestionnaireStrings[Key] extends (
  ...params: infer Params
) => string
  ? Params
  : []

/**
 * A host's translation. Partial: whatever it leaves out stays English, so a
 * catalogue can be filled in over time and a key added by a later release
 * never leaves a blank on the screen.
 */
export type StringOverrides = Partial<QuestionnaireStrings>

/**
 * How a component asks for a string.
 *
 * The spread is empty for a key that stands on its own and required for one
 * that does not, so neither can be looked up the wrong way round.
 */
export type Translate = <Key extends StringKey>(key: Key, ...params: ParamsOf<Key>) => string

/** *overrides* laid over the English defaults. */
export function resolveStrings(overrides?: StringOverrides): QuestionnaireStrings {
  if (!overrides) return defaultStrings
  return { ...defaultStrings, ...overrides }
}

/** Read *key*, falling back to the English entry where a catalogue has none. */
export function translate<Key extends StringKey>(
  strings: StringOverrides,
  key: Key,
  ...params: ParamsOf<Key>
): string {
  const value = strings[key] ?? defaultStrings[key]
  if (typeof value !== "function") return value
  // Loosened deliberately: each key has parameters of its own, and spreading a
  // generic tuple into that union is more than the checker will follow. The
  // signature above is where the types are kept honest.
  return (value as (...params: unknown[]) => string)(...(params as unknown[]))
}

/** A `Translate` bound to one catalogue. */
export function translator(strings: StringOverrides): Translate {
  return (key, ...params) => translate(strings, key, ...params)
}
