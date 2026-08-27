/**
 * The wire format, as emitted by `vinta_django_questionnaires.plan`.
 *
 * Nothing here is inferred or guessed: every field is written by the server,
 * messages included, so the two sides cannot disagree about what a rule says.
 */

/** A check the client knows how to apply from its own table. */
export interface NativeCheck {
  kind: string
  /** The validator that emitted it -- the identity shared with the server. */
  validator: string
  errorKey: string
  args: unknown[]
  params: Record<string, unknown>
  /** May still contain `{placeholders}` only the failure can fill. */
  message: string
  skipWhenEmpty: boolean
}

/** A check only an implementation registered under `validator` can apply. */
export interface CustomCheck {
  kind: "custom"
  validator: string
  params: Record<string, unknown>
  messages: Record<string, string>
  serverOnly: boolean
  skipWhenEmpty: boolean
}

export type PlanCheck = NativeCheck | CustomCheck

export interface ChoicePlan {
  value: string
  label: string
}

export interface QuestionPlan {
  key: string
  type: string
  title: string
  description: string
  condition: string
  checks: PlanCheck[]
  /** Advisory: whether any check reads what earlier ones recorded. */
  usesContext: boolean
  /** The widget the server resolved: this question's, or its type's default. */
  widget: string | null
  /** The widget's defaults, with this question's props over the top. */
  widgetProps: Record<string, unknown>
  /** The narrowest this question may be rendered, per window size range. */
  minimumColumns: Record<string, number>
  requiresBeingFirstInARow: boolean
  requiresBeingLastInARow: boolean
  itemType?: string
  choices?: ChoicePlan[]
  allowsOther?: boolean
  matrix?: { rows: ChoicePlan[]; columns: ChoicePlan[] }
  valueSet?: ValueSetRef
  subQuestionnaire?:
    QuestionnairePlan | { ref: { questionnaire: string; version: number } } | null
}

export interface ValueSetRef {
  key: string
  source: string
  /** Whether the options come from an endpoint the client calls itself. */
  resolvedByTheClient: boolean
}

export interface SectionPlan {
  key: string
  title: string
  description: string
  conclusion: string
  defaultState: "open" | "closed"
  condition: string
  /** Grid columns this section resolved to, per window size range. */
  columns: Record<string, number>
  questions: QuestionPlan[]
}

export interface PagePlan {
  key: string
  title: string
  description: string
  conclusion: string
  condition: string
  /** Whether the respondent may leave this page for later and move on. */
  isSkippable: boolean
  /** Grid columns this page resolved to, per window size range. */
  columns: Record<string, number>
  sections: SectionPlan[]
}

export interface WindowSizeRangePlan {
  key: string
  label: string
  minWidth: number
  maxWidth: number | null
}

export interface QuestionnairePlan {
  planVersion: number
  questionnaire: string
  version: number
  title: string
  description: string
  /** The breakpoints this questionnaire is laid out against. */
  windowSizeRanges: WindowSizeRangePlan[]
  columns: Record<string, number>
  pages: PagePlan[]
}

/** The plan version this client was written against. */
export const SUPPORTED_PLAN_VERSION = 1

export function isCustomCheck(check: PlanCheck): check is CustomCheck {
  return check.kind === "custom"
}

export function isExpandedSubQuestionnaire(
  sub: QuestionPlan["subQuestionnaire"],
): sub is QuestionnairePlan {
  return !!sub && "pages" in sub
}
