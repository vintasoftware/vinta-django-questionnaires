/**
 * A definition, as the plan it would become.
 *
 * The editor holds a document being typed into; the renderer reads a plan the
 * server resolved. Between a keystroke and a save there is no plan, so a
 * preview either waits for a round trip on every character or resolves the same
 * things locally. This does the second.
 *
 * It is a preview, and says so: it resolves what the catalog can tell it --
 * which widget a type defaults to, which props that widget fills in, which
 * columns a layer inherits -- and leaves what only the database knows. A value
 * set's options are not here, a nested questionnaire's pages are not here, and
 * a validator's message templates are the catalog's rather than the ones the
 * server would render. What it does get right is everything an author is
 * looking at the preview to check: the shape of the page, the widget each
 * question lands on, and how wide it is at each breakpoint.
 */

import {
  defaultWidgetFor,
  questionTypeInfo,
  type EditorCatalog,
  type PageDefinition,
  type QuestionDefinition,
  type QuestionnaireDefinition,
  type SectionDefinition,
} from "./definition.js"
import type {
  ChoicePlan,
  PagePlan,
  PlanCheck,
  QuestionPlan,
  QuestionnairePlan,
  SectionPlan,
} from "./plan.js"
import { SUPPORTED_PLAN_VERSION } from "./plan.js"

/** The plan the server would build from *document*, as far as can be told here. */
export function planFromDefinition(
  document: QuestionnaireDefinition,
  catalog: EditorCatalog | null,
): QuestionnairePlan {
  return {
    planVersion: SUPPORTED_PLAN_VERSION,
    questionnaire: document.questionnaire.key,
    version: document.version,
    title: document.title || document.questionnaire.name,
    description: document.description,
    windowSizeRanges: document.windowSizeRanges.map((range) => ({
      key: range.key,
      label: range.label,
      minWidth: range.minWidth,
      maxWidth: range.maxWidth,
    })),
    columns: { ...document.columns },
    pages: document.pages.map((page) => pagePlan(page, catalog)),
  }
}

function pagePlan(page: PageDefinition, catalog: EditorCatalog | null): PagePlan {
  return {
    key: page.key,
    title: page.title,
    description: page.description,
    conclusion: page.conclusion,
    condition: page.condition,
    isSkippable: page.isSkippable,
    columns: { ...page.columns },
    sections: page.sections.map((section) => sectionPlan(section, catalog)),
  }
}

function sectionPlan(section: SectionDefinition, catalog: EditorCatalog | null): SectionPlan {
  return {
    key: section.key,
    title: section.title,
    description: section.description,
    conclusion: section.conclusion,
    defaultState: section.defaultState,
    condition: section.condition,
    columns: { ...section.columns },
    questions: section.questions.map((question) => questionPlan(question, catalog)),
  }
}

function questionPlan(
  question: QuestionDefinition,
  catalog: EditorCatalog | null,
): QuestionPlan {
  const info = catalog ? questionTypeInfo(catalog, question.questionType) : undefined
  const widget = resolveWidgetInfo(question, catalog)
  const choices = activeChoices(question, "option")

  const plan: QuestionPlan = {
    key: question.key,
    type: question.questionType,
    title: question.title,
    description: question.description,
    condition: question.condition,
    checks: question.validators.filter((entry) => entry.isEnabled).map(previewCheck),
    usesContext: false,
    // The server writes `resolved.widget` on the way out, so a document that
    // has been saved already knows the answer; the catalog covers the rest.
    widget: question.resolved?.widget ?? question.widget ?? widget?.key ?? null,
    widgetProps: { ...(widget?.defaultProps ?? {}), ...question.widgetProps },
    minimumColumns: { ...question.minimumColumns },
    requiresBeingFirstInARow: question.requiresBeingFirstInARow,
    requiresBeingLastInARow: question.requiresBeingLastInARow,
  }

  if (info?.requiresItemType) plan.itemType = question.itemQuestionType
  if (info?.supportsChoices && !info.usesMatrixAxes) plan.choices = choices
  if (info?.supportsOtherOption) {
    plan.allowsOther = question.allowsOther
    plan.otherLabel = question.otherLabel
  }
  if (info?.usesMatrixAxes) {
    plan.matrix = {
      rows: activeChoices(question, "row"),
      columns: activeChoices(question, "column"),
    }
  }
  if (question.valueSet) {
    const found = catalog?.valueSets.find((entry) => entry.key === question.valueSet)
    plan.valueSet = {
      key: question.valueSet,
      source: found?.source ?? "",
      resolvedByTheClient: found?.resolvedByTheClient ?? false,
    }
  }
  // Nesting is left as a reference rather than guessed at: the pages of another
  // version are not in the document being edited, and inventing them would show
  // an author a form that does not exist.
  if (info?.requiresSubQuestionnaire && question.subQuestionnaire) {
    plan.subQuestionnaire = {
      ref: {
        questionnaire: question.subQuestionnaire,
        version: question.subQuestionnaireVersion ?? 0,
      },
    }
  }
  return plan
}

/** The widget this question would resolve to: its own, or its type's default. */
function resolveWidgetInfo(question: QuestionDefinition, catalog: EditorCatalog | null) {
  if (!catalog) return undefined
  if (question.widget) return catalog.widgets.find((entry) => entry.key === question.widget)
  return defaultWidgetFor(catalog, question.questionType)
}

function activeChoices(question: QuestionDefinition, axis: string): ChoicePlan[] {
  return question.choices
    .filter((choice) => choice.axis === axis && choice.isActive)
    .map((choice) => ({ value: choice.value, label: choice.label }))
}

/**
 * A validator binding as the check the renderer reads.
 *
 * Only enough of one to be recognised: the preview marks a required question
 * and says a check exists, it does not run any. The server phrases the real
 * messages, and does so against answers, which a preview has none of.
 */
function previewCheck(binding: {
  validator: string
  params: Record<string, unknown>
  messageOverrides: Record<string, string>
}): PlanCheck {
  return {
    kind: "custom",
    validator: binding.validator,
    params: { ...binding.params },
    messages: { ...binding.messageOverrides },
    serverOnly: false,
    skipWhenEmpty: false,
  }
}
