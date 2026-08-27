/**
 * The editor's state, as a reducer that knows nothing about React.
 *
 * Everything the editor does to a questionnaire happens here: adding a page,
 * reordering a validator chain, setting how many columns a section takes on a
 * phone. Keeping it a pure function of `(state, action)` means the rules can be
 * tested without rendering anything, and means the same state can drive a
 * different interface than the one shipped in `editor/`.
 *
 * Nodes are addressed by position -- `{ page: 0, section: 1, question: 2 }` --
 * which serialises to the very path the server reports its own issues against,
 * so a failure the server sends back lands on the field that caused it.
 */

import {
  NON_FIELD,
  SUPPORTED_DOCUMENT_VERSION,
  questionTypeInfo,
  type ChoiceDefinition,
  type DefinitionIssue,
  type EditorCatalog,
  type PageDefinition,
  type QuestionDefinition,
  type QuestionnaireDefinition,
  type SectionDefinition,
  type ValidatorDefinition,
  type WindowSizeRangeDefinition,
} from "./definition.js"

// -------------------------------------------------------------------- paths

export interface PagePath {
  page: number
}
export interface SectionPath extends PagePath {
  section: number
}
export interface QuestionPath extends SectionPath {
  question: number
}

/** Whatever the editor can have selected. */
export type Selection =
  | { kind: "version" }
  | ({ kind: "page" } & PagePath)
  | ({ kind: "section" } & SectionPath)
  | ({ kind: "question" } & QuestionPath)

export type NodePath = PagePath | SectionPath | QuestionPath

export type ItemList = "choices" | "validators"

/** The dotted path the server addresses the same node by. */
export function pathOf(target: Selection | NodePath | null): string {
  if (!target) return ""
  const parts: string[] = []
  if ("page" in target) parts.push(`pages.${target.page}`)
  if ("section" in target) parts.push(`sections.${target.section}`)
  if ("question" in target) parts.push(`questions.${target.question}`)
  return parts.join(".")
}

/** The issues reported against one node, keyed by field. */
export function issuesAt(
  issues: readonly DefinitionIssue[],
  path: string,
): Record<string, string[]> {
  const merged: Record<string, string[]> = {}
  for (const issue of issues) {
    if (issue.path !== path) continue
    for (const [field, messages] of Object.entries(issue.errors)) {
      merged[field] = [...(merged[field] ?? []), ...messages]
    }
  }
  return merged
}

/** Whether anything is reported against *path* or anything under it. */
export function hasIssuesUnder(issues: readonly DefinitionIssue[], path: string): boolean {
  return issues.some((issue) => issue.path === path || issue.path.startsWith(`${path}.`))
}

// ------------------------------------------------------------------ reading

export function pageAt(
  document: QuestionnaireDefinition,
  path: PagePath,
): PageDefinition | undefined {
  return document.pages[path.page]
}

export function sectionAt(
  document: QuestionnaireDefinition,
  path: SectionPath,
): SectionDefinition | undefined {
  return pageAt(document, path)?.sections[path.section]
}

export function questionAt(
  document: QuestionnaireDefinition,
  path: QuestionPath,
): QuestionDefinition | undefined {
  return sectionAt(document, path)?.questions[path.question]
}

/** Every question of the document, with where it sits. */
export function allQuestions(
  document: QuestionnaireDefinition,
): { path: QuestionPath; question: QuestionDefinition }[] {
  const found: { path: QuestionPath; question: QuestionDefinition }[] = []
  document.pages.forEach((page, pageIndex) =>
    page.sections.forEach((section, sectionIndex) =>
      section.questions.forEach((question, questionIndex) =>
        found.push({
          path: { page: pageIndex, section: sectionIndex, question: questionIndex },
          question,
        }),
      ),
    ),
  )
  return found
}

// ----------------------------------------------------------- new nodes

const NOT_KEY_SAFE = /[^a-z0-9]+/g

/** What Django's `SlugField` accepts, which is what every key here is. */
const KEY_PATTERN = /^[-a-zA-Z0-9_]+$/

/** A key from a title, of a shape `KEY_PATTERN` accepts. */
export function slugify(value: string): string {
  return value
    .toLowerCase()
    .replace(NOT_KEY_SAFE, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 100)
}

/** *base*, or `base-2`, `base-3`... until it is not one of *taken*. */
export function uniqueKey(base: string, taken: Iterable<string>): string {
  const used = new Set(taken)
  const stem = base || "item"
  if (!used.has(stem)) return stem
  let counter = 2
  while (used.has(`${stem}-${counter}`)) counter += 1
  return `${stem}-${counter}`
}

export function newPage(taken: Iterable<string>): PageDefinition {
  return {
    key: uniqueKey("page", taken),
    title: "Untitled page",
    description: "",
    conclusion: "",
    condition: "",
    isSkippable: false,
    columns: {},
    sections: [],
  }
}

export function newSection(taken: Iterable<string>): SectionDefinition {
  return {
    key: uniqueKey("section", taken),
    title: "Untitled section",
    description: "",
    conclusion: "",
    defaultState: "open",
    condition: "",
    columns: {},
    questions: [],
  }
}

export function newQuestion(
  taken: Iterable<string>,
  questionType = "free_text",
): QuestionDefinition {
  return {
    key: uniqueKey("question", taken),
    title: "Untitled question",
    description: "",
    questionType,
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
  }
}

export function newChoice(taken: Iterable<string>): ChoiceDefinition {
  const value = uniqueKey("option", taken)
  return { axis: "option", value, label: value, extra: {}, isActive: true }
}

export function newValidator(validator = "required"): ValidatorDefinition {
  return { validator, params: {}, messageOverrides: {}, isEnabled: true }
}

export function newRange(taken: Iterable<string>): WindowSizeRangeDefinition {
  return { key: uniqueKey("range", taken), label: "", minWidth: 0, maxWidth: null }
}

/** An empty document, for authoring a version that has nothing in it yet. */
export function emptyDocument(
  questionnaire: { key: string; name: string },
  version = 1,
): QuestionnaireDefinition {
  return {
    documentVersion: SUPPORTED_DOCUMENT_VERSION,
    questionnaire,
    version,
    title: questionnaire.name,
    description: "",
    status: "draft",
    editPolicy: "",
    responsesDueAt: null,
    editsDueAt: null,
    windowSizeRanges: [],
    columns: {},
    pages: [],
  }
}

// ------------------------------------------------------------------ actions

export type EditorAction =
  /** Replace everything, as after a fetch. */
  | { type: "loaded"; document: QuestionnaireDefinition }
  /** Replace everything and treat it as agreed with the server. */
  | { type: "saved"; document: QuestionnaireDefinition }
  | { type: "select"; selection: Selection }
  | { type: "issues"; issues: DefinitionIssue[] }
  | { type: "patchVersion"; patch: Partial<QuestionnaireDefinition> }
  | { type: "patch"; path: NodePath; patch: Record<string, unknown> }
  | { type: "insert"; path: NodePath | null; index?: number }
  | { type: "remove"; path: NodePath }
  | { type: "move"; path: NodePath; by: number }
  /** Drag and drop: `path` is the *parent*, `null` for the list of pages. */
  | { type: "reorder"; path: NodePath | null; from: number; to: number }
  | { type: "patchItem"; path: QuestionPath; list: ItemList; index: number; patch: object }
  | { type: "insertItem"; path: QuestionPath; list: ItemList }
  | { type: "removeItem"; path: QuestionPath; list: ItemList; index: number }
  | { type: "moveItem"; path: QuestionPath; list: ItemList; index: number; by: number }
  | { type: "reorderItem"; path: QuestionPath; list: ItemList; from: number; to: number }
  /** `columns: null` clears the declaration, so the layer inherits again. */
  | { type: "setColumns"; path: NodePath | null; range: string; columns: number | null }
  | { type: "setMinimumColumns"; path: QuestionPath; range: string; columns: number | null }
  | { type: "patchRange"; index: number; patch: Partial<WindowSizeRangeDefinition> }
  | { type: "insertRange" }
  | { type: "removeRange"; index: number }

export interface EditorState {
  document: QuestionnaireDefinition
  /** What the server last agreed to, for telling whether anything is unsaved. */
  saved: QuestionnaireDefinition
  selection: Selection
  issues: DefinitionIssue[]
}

export function initialState(document: QuestionnaireDefinition): EditorState {
  return { document, saved: document, selection: { kind: "version" }, issues: [] }
}

// -- immutable helpers -------------------------------------------------

function replace<T>(items: readonly T[], index: number, item: T): T[] {
  return items.map((existing, position) => (position === index ? item : existing))
}

function reordered<T>(items: readonly T[], from: number, to: number): T[] {
  if (from === to || from < 0 || from >= items.length || to < 0 || to >= items.length) {
    return [...items]
  }
  const next = [...items]
  const [item] = next.splice(from, 1)
  next.splice(to, 0, item as T)
  return next
}

function moved<T>(items: readonly T[], index: number, by: number): T[] {
  const target = index + by
  if (index < 0 || index >= items.length || target < 0 || target >= items.length) {
    return [...items]
  }
  const next = [...items]
  const [item] = next.splice(index, 1)
  next.splice(target, 0, item as T)
  return next
}

function withoutKeys(mapping: Record<string, number>, range: string): Record<string, number> {
  const next = { ...mapping }
  delete next[range]
  return next
}

function isQuestionPath(path: NodePath): path is QuestionPath {
  return "question" in path
}

function isSectionPath(path: NodePath): path is SectionPath {
  return "section" in path && !("question" in path)
}

/** Rewrite the question at *path*, leaving everything else alone. */
function mapQuestion(
  document: QuestionnaireDefinition,
  path: QuestionPath,
  change: (question: QuestionDefinition) => QuestionDefinition,
): QuestionnaireDefinition {
  return mapSection(document, path, (section) => {
    const question = section.questions[path.question]
    if (!question) return section
    return {
      ...section,
      questions: replace(section.questions, path.question, change(question)),
    }
  })
}

function mapSection(
  document: QuestionnaireDefinition,
  path: SectionPath,
  change: (section: SectionDefinition) => SectionDefinition,
): QuestionnaireDefinition {
  return mapPage(document, path, (page) => {
    const section = page.sections[path.section]
    if (!section) return page
    return { ...page, sections: replace(page.sections, path.section, change(section)) }
  })
}

function mapPage(
  document: QuestionnaireDefinition,
  path: PagePath,
  change: (page: PageDefinition) => PageDefinition,
): QuestionnaireDefinition {
  const page = document.pages[path.page]
  if (!page) return document
  return { ...document, pages: replace(document.pages, path.page, change(page)) }
}

/**
 * Rewrite one of a question's two lists, keeping both of them typed.
 *
 * The change is generic over the item, so it can reorder or drop entries
 * without knowing which list it is looking at.
 */
function mapItems(
  question: QuestionDefinition,
  list: ItemList,
  change: <T>(items: readonly T[]) => T[],
): QuestionDefinition {
  return list === "choices"
    ? { ...question, choices: change(question.choices) }
    : { ...question, validators: change(question.validators) }
}

function patchNode(
  document: QuestionnaireDefinition,
  path: NodePath,
  patch: Record<string, unknown>,
): QuestionnaireDefinition {
  if (isQuestionPath(path)) {
    return mapQuestion(document, path, (question) => ({ ...question, ...patch }))
  }
  if (isSectionPath(path)) {
    return mapSection(document, path, (section) => ({ ...section, ...patch }))
  }
  return mapPage(document, path, (page) => ({ ...page, ...patch }))
}

function keysUnder(document: QuestionnaireDefinition, path: NodePath | null): string[] {
  if (path === null) return document.pages.map((page) => page.key)
  if (isSectionPath(path)) {
    // A question key has to be unique across the whole version, not the section.
    return allQuestions(document).map(({ question }) => question.key)
  }
  return (pageAt(document, path)?.sections ?? []).map((section) => section.key)
}

function insertNode(
  document: QuestionnaireDefinition,
  path: NodePath | null,
  index?: number,
): QuestionnaireDefinition {
  const taken = keysUnder(document, path)
  if (path === null) {
    const pages = [...document.pages]
    pages.splice(index ?? pages.length, 0, newPage(taken))
    return { ...document, pages }
  }
  if (isSectionPath(path)) {
    return mapSection(document, path, (section) => {
      const questions = [...section.questions]
      questions.splice(index ?? questions.length, 0, newQuestion(taken))
      return { ...section, questions }
    })
  }
  return mapPage(document, path, (page) => {
    const sections = [...page.sections]
    sections.splice(index ?? sections.length, 0, newSection(taken))
    return { ...page, sections }
  })
}

function removeNode(
  document: QuestionnaireDefinition,
  path: NodePath,
): QuestionnaireDefinition {
  if (isQuestionPath(path)) {
    return mapSection(document, path, (section) => ({
      ...section,
      questions: section.questions.filter((_, index) => index !== path.question),
    }))
  }
  if (isSectionPath(path)) {
    return mapPage(document, path, (page) => ({
      ...page,
      sections: page.sections.filter((_, index) => index !== path.section),
    }))
  }
  return { ...document, pages: document.pages.filter((_, index) => index !== path.page) }
}

/** Reorder the children of *path* -- its sections, its questions, or the pages. */
function reorderNodes(
  document: QuestionnaireDefinition,
  path: NodePath | null,
  from: number,
  to: number,
): QuestionnaireDefinition {
  if (path === null) {
    return { ...document, pages: reordered(document.pages, from, to) }
  }
  if (isSectionPath(path)) {
    return mapSection(document, path, (section) => ({
      ...section,
      questions: reordered(section.questions, from, to),
    }))
  }
  return mapPage(document, path, (page) => ({
    ...page,
    sections: reordered(page.sections, from, to),
  }))
}

function moveNode(
  document: QuestionnaireDefinition,
  path: NodePath,
  by: number,
): QuestionnaireDefinition {
  if (isQuestionPath(path)) {
    return mapSection(document, path, (section) => ({
      ...section,
      questions: moved(section.questions, path.question, by),
    }))
  }
  if (isSectionPath(path)) {
    return mapPage(document, path, (page) => ({
      ...page,
      sections: moved(page.sections, path.section, by),
    }))
  }
  return { ...document, pages: moved(document.pages, path.page, by) }
}

function setColumns(
  document: QuestionnaireDefinition,
  path: NodePath | null,
  range: string,
  columns: number | null,
): QuestionnaireDefinition {
  const change = (mapping: Record<string, number>) =>
    columns === null ? withoutKeys(mapping, range) : { ...mapping, [range]: columns }
  if (path === null) return { ...document, columns: change(document.columns) }
  if (isSectionPath(path)) {
    return mapSection(document, path, (section) => ({
      ...section,
      columns: change(section.columns),
    }))
  }
  if (isQuestionPath(path)) return document
  return mapPage(document, path, (page) => ({ ...page, columns: change(page.columns) }))
}

/** Where the selection should land once *path* is gone. */
function selectionAfterRemoval(selection: Selection, path: NodePath): Selection {
  if (selection.kind === "version") return selection
  const removed = pathOf(path)
  const current = pathOf(selection)
  if (current === removed || current.startsWith(`${removed}.`)) {
    if (isQuestionPath(path)) return { kind: "section", page: path.page, section: path.section }
    if (isSectionPath(path)) return { kind: "page", page: path.page }
    return { kind: "version" }
  }
  return selection
}

/** Where the selection ends up once its container has been reordered.

    A selection is affected when it lives *in* the container that moved -- a
    question selected inside a page that moved keeps its question, and changes
    its page index. */
function selectionAfterReorder(
  selection: Selection,
  path: NodePath | null,
  from: number,
  to: number,
): Selection {
  if (selection.kind === "version") return selection

  const shift = (index: number) =>
    index === from
      ? to
      : index > from && index <= to
        ? index - 1
        : index < from && index >= to
          ? index + 1
          : index

  if (path === null) {
    return { ...selection, page: shift(selection.page) }
  }
  if (isSectionPath(path)) {
    const inside =
      "question" in selection &&
      selection.page === path.page &&
      selection.section === path.section
    return inside ? { ...selection, question: shift(selection.question) } : selection
  }
  const inside = "section" in selection && selection.page === path.page
  return inside ? { ...selection, section: shift(selection.section) } : selection
}

export function editorReducer(state: EditorState, action: EditorAction): EditorState {
  switch (action.type) {
    case "loaded":
      return initialState(action.document)
    case "saved":
      return { ...state, document: action.document, saved: action.document, issues: [] }
    case "select":
      return { ...state, selection: action.selection }
    case "issues":
      return { ...state, issues: action.issues }
    case "patchVersion":
      return { ...state, document: { ...state.document, ...action.patch } }
    case "patch":
      return { ...state, document: patchNode(state.document, action.path, action.patch) }
    case "insert":
      return { ...state, document: insertNode(state.document, action.path, action.index) }
    case "remove":
      return {
        ...state,
        document: removeNode(state.document, action.path),
        selection: selectionAfterRemoval(state.selection, action.path),
      }
    case "move":
      return { ...state, document: moveNode(state.document, action.path, action.by) }
    case "reorder":
      return {
        ...state,
        document: reorderNodes(state.document, action.path, action.from, action.to),
        // What was selected moved with it, so the selection follows.
        selection: selectionAfterReorder(state.selection, action.path, action.from, action.to),
      }
    case "patchItem":
      return {
        ...state,
        document: mapQuestion(state.document, action.path, (question) =>
          action.list === "choices"
            ? {
                ...question,
                choices: replace(question.choices, action.index, {
                  ...(question.choices[action.index] as ChoiceDefinition),
                  ...action.patch,
                }),
              }
            : {
                ...question,
                validators: replace(question.validators, action.index, {
                  ...(question.validators[action.index] as ValidatorDefinition),
                  ...action.patch,
                }),
              },
        ),
      }
    case "insertItem":
      return {
        ...state,
        document: mapQuestion(state.document, action.path, (question) =>
          action.list === "choices"
            ? {
                ...question,
                choices: [
                  ...question.choices,
                  newChoice(question.choices.map((choice) => choice.value)),
                ],
              }
            : { ...question, validators: [...question.validators, newValidator()] },
        ),
      }
    case "removeItem":
      return {
        ...state,
        document: mapQuestion(state.document, action.path, (question) =>
          mapItems(question, action.list, (items) =>
            items.filter((_, index) => index !== action.index),
          ),
        ),
      }
    case "moveItem":
      return {
        ...state,
        document: mapQuestion(state.document, action.path, (question) =>
          mapItems(question, action.list, (items) => moved(items, action.index, action.by)),
        ),
      }
    case "reorderItem":
      return {
        ...state,
        document: mapQuestion(state.document, action.path, (question) =>
          mapItems(question, action.list, (items) => reordered(items, action.from, action.to)),
        ),
      }
    case "setColumns":
      return {
        ...state,
        document: setColumns(state.document, action.path, action.range, action.columns),
      }
    case "setMinimumColumns":
      return {
        ...state,
        document: mapQuestion(state.document, action.path, (question) => ({
          ...question,
          minimumColumns:
            action.columns === null
              ? withoutKeys(question.minimumColumns, action.range)
              : { ...question.minimumColumns, [action.range]: action.columns },
        })),
      }
    case "patchRange":
      return {
        ...state,
        document: {
          ...state.document,
          windowSizeRanges: replace(state.document.windowSizeRanges, action.index, {
            ...(state.document.windowSizeRanges[action.index] as WindowSizeRangeDefinition),
            ...action.patch,
          }),
        },
      }
    case "insertRange":
      return {
        ...state,
        document: {
          ...state.document,
          windowSizeRanges: [
            ...state.document.windowSizeRanges,
            newRange(state.document.windowSizeRanges.map((range) => range.key)),
          ],
        },
      }
    case "removeRange":
      return {
        ...state,
        document: {
          ...state.document,
          windowSizeRanges: state.document.windowSizeRanges.filter(
            (_, index) => index !== action.index,
          ),
        },
      }
    default:
      return state
  }
}

// ------------------------------------------------------------------- saving

/** The document as it goes back: without what only the server writes. */
export function outgoingDocument(document: QuestionnaireDefinition): QuestionnaireDefinition {
  const { state: _state, ...rest } = document
  return {
    ...rest,
    pages: document.pages.map((page) => ({
      ...page,
      sections: page.sections.map((section) => ({
        ...section,
        questions: section.questions.map(({ resolved: _resolved, ...question }) => question),
      })),
    })),
  }
}

/** Whether anything has changed since the server last agreed to it. */
export function isDirty(state: EditorState): boolean {
  return (
    JSON.stringify(outgoingDocument(state.document)) !==
    JSON.stringify(outgoingDocument(state.saved))
  )
}

/** The keys whose questions were dropped or renamed -- whose answers are orphaned. */
export function orphanedQuestionKeys(state: EditorState): string[] {
  const current = new Set(allQuestions(state.document).map(({ question }) => question.key))
  return allQuestions(state.saved)
    .map(({ question }) => question.key)
    .filter((key) => !current.has(key))
}

// --------------------------------------------------------------- validation

/**
 * What the editor can tell is wrong before asking the server.
 *
 * It is deliberately not a reimplementation of the server's rules -- the server
 * has the last word, and says so through `DefinitionIssue`s of the same shape.
 * This is the subset worth catching while someone types: keys that are missing,
 * clash or would not survive a slug field, and configuration a question type
 * plainly does not take.
 */
export function validateDefinition(
  document: QuestionnaireDefinition,
  catalog: EditorCatalog | null,
): DefinitionIssue[] {
  const issues: DefinitionIssue[] = []
  const add = (path: string, field: string, message: string) =>
    issues.push({ path, errors: { [field]: [message] } })

  const questionKeys = new Map<string, number>()
  for (const { question } of allQuestions(document)) {
    questionKeys.set(question.key, (questionKeys.get(question.key) ?? 0) + 1)
  }

  const pageKeys = new Set<string>()
  document.pages.forEach((page, pageIndex) => {
    const pagePath = `pages.${pageIndex}`
    checkKey(page.key, pagePath, add)
    if (pageKeys.has(page.key)) add(pagePath, "key", "Another page already uses this key.")
    pageKeys.add(page.key)
    if (!page.title.trim()) add(pagePath, "title", "A page needs a title.")

    const sectionKeys = new Set<string>()
    page.sections.forEach((section, sectionIndex) => {
      const sectionPath = `${pagePath}.sections.${sectionIndex}`
      checkKey(section.key, sectionPath, add)
      if (sectionKeys.has(section.key))
        add(sectionPath, "key", "Another section of this page already uses this key.")
      sectionKeys.add(section.key)
      if (!section.title.trim()) add(sectionPath, "title", "A section needs a title.")

      section.questions.forEach((question, questionIndex) => {
        const path = `${sectionPath}.questions.${questionIndex}`
        checkKey(question.key, path, add)
        if ((questionKeys.get(question.key) ?? 0) > 1)
          add(path, "key", "Another question of this version already uses this key.")
        if (!question.title.trim()) add(path, "title", "A question needs a title.")
        checkQuestionType(question, path, catalog, add)
        checkChoices(question, path, add)
      })
    })
  })

  return issues
}

type Report = (path: string, field: string, message: string) => void

function checkKey(key: string, path: string, add: Report): void {
  if (!key.trim()) {
    add(path, "key", "A key is required -- answers are stored against it.")
  } else if (!KEY_PATTERN.test(key)) {
    add(path, "key", "A key may hold letters, digits, hyphens and underscores only.")
  }
}

function checkQuestionType(
  question: QuestionDefinition,
  path: string,
  catalog: EditorCatalog | null,
  add: Report,
): void {
  if (!catalog) return
  const info = questionTypeInfo(catalog, question.questionType)
  if (!info) {
    add(path, "questionType", "Pick a question type.")
    return
  }
  if (info.requiresItemType && !question.itemQuestionType)
    add(path, "itemQuestionType", "A list of items needs the type of its items.")
  if (!info.requiresItemType && question.itemQuestionType)
    add(path, "itemQuestionType", "Only a list of items takes an item type.")
  if (info.requiresSubQuestionnaire && !question.subQuestionnaire)
    add(path, "subQuestionnaire", "This question type needs a sub-questionnaire.")
  if (!info.requiresSubQuestionnaire && question.subQuestionnaire)
    add(path, "subQuestionnaire", "Only a sub-questionnaire question nests another one.")
  if (info.supportsValueSet && !info.supportsChoices && !question.valueSet)
    add(path, "valueSet", "This question type needs a value set.")
  if (!info.supportsValueSet && question.valueSet)
    add(path, "valueSet", "This question type does not take a value set.")
  if (!info.supportsOtherOption && question.allowsOther)
    add(path, "allowsOther", "This question type does not take an other option.")
  if (!info.supportsChoices && question.choices.length)
    add(path, "choices", "This question type does not take choices.")

  for (const [index, binding] of question.validators.entries()) {
    const info = catalog.validators.find((entry) => entry.key === binding.validator)
    if (!info) {
      add(`${path}.validators.${index}`, "validator", "There is no validator with this key.")
    } else if (info.questionTypes && !info.questionTypes.includes(question.questionType)) {
      add(
        `${path}.validators.${index}`,
        "validator",
        `${info.label} does not apply to this question type.`,
      )
    }
  }
}

function checkChoices(question: QuestionDefinition, path: string, add: Report): void {
  const seen = new Set<string>()
  question.choices.forEach((choice, index) => {
    const key = `${choice.axis}:${choice.value}`
    if (!choice.value.trim()) {
      add(
        `${path}.choices.${index}`,
        "value",
        "A choice needs a value -- it is what is stored.",
      )
    } else if (seen.has(key)) {
      add(`${path}.choices.${index}`, "value", "Another choice already uses this value.")
    }
    seen.add(key)
  })
}

/** A single flat message per issue, for somewhere with no room for a form. */
export function summariseIssues(issues: readonly DefinitionIssue[]): string[] {
  return issues.flatMap((issue) =>
    Object.entries(issue.errors).flatMap(([field, messages]) =>
      messages.map((message) =>
        field === NON_FIELD || !field
          ? `${issue.path || "questionnaire"}: ${message}`
          : `${issue.path || "questionnaire"} ${field}: ${message}`,
      ),
    ),
  )
}
