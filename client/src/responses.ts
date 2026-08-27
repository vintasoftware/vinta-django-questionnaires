/**
 * The shapes the response API speaks.
 *
 * Types only: how the requests are made -- fetch, axios, a framework's own
 * data layer -- is the host app's business, and the endpoints are plain JSON:
 *
 * ```
 * POST /responses/                              open a response
 * GET  /responses/<id>/                         where the respondent is
 * POST /responses/<id>/pages/<key>/             push one page's answers
 * POST /responses/<id>/pages/<key>/skip/        leave a page for later
 * ```
 */

import type { QuestionnairePlan } from "./plan.js"

export type ResponseStatus = "in_progress" | "completed" | "abandoned"
export type PageResponseStatus = "completed" | "skipped"
export type SkipReason = "manual_action" | "false_condition"

export interface ResponseProgress {
  /** Page keys that have been filled in. */
  completed: string[]
  skipped: { page: string; reason: SkipReason }[]
  /** Page keys still waiting on the respondent, in order.  A manual skip is
   *  still pending: skipping means later, not never. */
  pending: string[]
  /** The page to show: the first one still pending. */
  current: string | null
  isComplete: boolean
}

export type EditPolicy = "never" | "until_completed" | "always"

/** What the version still allows, as of this reply. */
export interface ResponsePolicy {
  editPolicy: EditPolicy
  /** Whether a page with no answers yet can still be answered. */
  canRespond: boolean
  /** Whether an answer already recorded can still be changed. */
  canEdit: boolean
  responsesDueAt: string | null
  editsDueAt: string | null
}

export interface QuestionnaireResponsePayload {
  id: string
  questionnaire: string
  version: number
  status: ResponseStatus
  answers: Record<string, unknown>
  progress: ResponseProgress
  policy: ResponsePolicy
  plan?: QuestionnairePlan
}

export interface PageResponsePayload {
  page: string
  status: PageResponseStatus
  skipReason: SkipReason | null
  submittedAt: string | null
}

export interface PageSubmitPayload {
  answers: Record<string, unknown>
}

export interface PageSubmitResult {
  page: PageResponsePayload
  response: QuestionnaireResponsePayload
}

/** The body of a 422: the issues that stopped the page, keyed by question. */
export interface ValidationErrorPayload {
  errors: Record<string, { validator: string; errorKey: string; message: string }[]>
}
