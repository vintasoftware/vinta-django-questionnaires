/**
 * Turning a plan into a Zod schema.
 *
 * Every check runs inside one `superRefine` rather than as a chain of native
 * Zod checks.  That is deliberate: the server skips checks on empty answers,
 * runs them in a fixed order, and lets later ones read what earlier ones
 * recorded.  Native Zod checks cannot express any of that, and a schema that
 * disagreed with the server would be worse than no schema at all.  The base
 * type is still Zod's, so a wrong shape is still a plain Zod type error.
 */

import { search } from "jmespath"
import { z } from "zod"

import { baseTypeFor } from "./baseTypes.js"
import { checks as checkTable } from "./checks.js"
import { ValidationContext } from "./context.js"
import { report, type DiagnosticReporter } from "./diagnostics.js"
import { formatMessage } from "./message.js"
import {
  isCustomCheck,
  isExpandedSubQuestionnaire,
  SUPPORTED_PLAN_VERSION,
  type PagePlan,
  type PlanCheck,
  type QuestionPlan,
  type QuestionnairePlan,
} from "./plan.js"
import { getClientValidator } from "./registry.js"
import { isEmpty, isTruthy } from "./values.js"

export interface BuildOptions {
  /** The whole answer set, so predicates can look at sibling questions. */
  answers?: Record<string, unknown>
  extra?: Record<string, unknown>
  /** Reported alongside any subscriber registered with `onDiagnostic`. */
  onDiagnostic?: DiagnosticReporter
}

export interface AnswerIssue {
  path: (string | number)[]
  validator: string
  errorKey: string
  message: string
}

const baseTypes = new WeakMap<QuestionPlan, z.ZodType>()

/**
 * The base type, made nullish.
 *
 * Whether an answer may be missing is decided by the plan -- by a `required`
 * check being there or not -- never by the base type.  The server works the
 * same way: an empty answer skips every validator except that one, so a base
 * type that rejected `null` outright would report a type error where the
 * server reports "this answer is required".
 */
function baseTypeOf(plan: QuestionPlan): z.ZodType {
  let base = baseTypes.get(plan)
  if (!base) {
    base = baseTypeFor(plan).nullish()
    baseTypes.set(plan, base)
  }
  return base
}

/** Run a question's checks, in order, against an already parsed value. */
export function runChecks(
  plan: QuestionPlan,
  value: unknown,
  context: ValidationContext,
  options: BuildOptions = {},
): AnswerIssue[] {
  const issues: AnswerIssue[] = []
  for (const check of plan.checks) {
    if (check.skipWhenEmpty && isEmpty(value)) {
      context.record({ validator: check.validator, valid: true, data: {} })
      continue
    }
    const found: AnswerIssue[] = []
    const fail = (
      errorKey: string,
      extra: Record<string, unknown> = {},
      template = "",
    ): void => {
      found.push({
        path: [],
        validator: check.validator,
        errorKey,
        message: formatMessage(template, { ...check.params, ...extra, value }),
      })
    }
    const data = applyCheck(check, value, context, fail, plan, options)
    issues.push(...found)
    context.record({ validator: check.validator, valid: found.length === 0, data: data ?? {} })
  }
  return issues
}

function applyCheck(
  check: PlanCheck,
  value: unknown,
  context: ValidationContext,
  fail: (errorKey: string, extra?: Record<string, unknown>, template?: string) => void,
  plan: QuestionPlan,
  options: BuildOptions,
): Record<string, unknown> | undefined {
  if (isCustomCheck(check)) {
    if (check.serverOnly) {
      report(
        {
          code: "server-only",
          validator: check.validator,
          questionKey: plan.key,
          message: `"${check.validator}" only runs on the server; it is checked on submit.`,
        },
        options.onDiagnostic,
      )
      return undefined
    }
    const implementation = getClientValidator(check.validator)
    if (!implementation) {
      report(
        {
          code: "missing-validator",
          validator: check.validator,
          questionKey: plan.key,
          message:
            `No client implementation is registered for "${check.validator}", so it is not ` +
            "checked in the browser. The server still enforces it.",
        },
        options.onDiagnostic,
      )
      return undefined
    }
    const outcome = implementation.validate(value, check.params, {
      chain: context,
      fail: (errorKey, params) => fail(errorKey, params, check.messages[errorKey] ?? ""),
    })
    return outcome?.data
  }

  const implementation = checkTable[check.kind]
  if (!implementation) {
    report(
      {
        code: "unknown-check",
        kind: check.kind,
        validator: check.validator,
        questionKey: plan.key,
        message:
          `This build does not know the check "${check.kind}" emitted by "${check.validator}". ` +
          "Upgrade the client package. The server still enforces it.",
      },
      options.onDiagnostic,
    )
    return undefined
  }
  const outcome = implementation({
    value,
    args: check.args,
    params: check.params,
    chain: context,
    fail: (errorKey, params) => fail(errorKey ?? check.errorKey, params, check.message),
  })
  return outcome?.data
}

/** Validate one answer, base type first, then the checks. */
export function validateAnswer(
  plan: QuestionPlan,
  value: unknown,
  options: BuildOptions = {},
): AnswerIssue[] {
  const parsed = baseTypeOf(plan).safeParse(value)
  if (!parsed.success) {
    return parsed.error.issues.map((issue) => ({
      path: issue.path.map((part) => part as string | number),
      validator: "",
      errorKey: "invalid_type",
      message: issue.message,
    }))
  }
  const context = new ValidationContext(options.answers ?? {}, options.extra ?? {})
  return runChecks(plan, parsed.data, context, options)
}

/** A Zod schema for one answer. */
export function buildQuestionSchema(plan: QuestionPlan, options: BuildOptions = {}): z.ZodType {
  return baseTypeOf(plan).superRefine((value, ctx) => {
    const context = new ValidationContext(options.answers ?? {}, options.extra ?? {})
    for (const issue of runChecks(plan, value, context, options)) {
      ctx.addIssue({
        code: "custom",
        message: issue.message,
        path: issue.path,
        params: { validator: issue.validator, errorKey: issue.errorKey },
      })
    }
  })
}

/** Whether a condition holds for *answers*, the way the server decides it. */
export function isApplicable(
  condition: string,
  answers: Record<string, unknown>,
  options: BuildOptions = {},
): boolean {
  if (!condition.trim()) return true
  try {
    return isTruthy(search(answers, condition))
  } catch (error) {
    report(
      {
        code: "condition-error",
        message: `Could not evaluate the condition ${JSON.stringify(condition)}: ${String(error)}`,
      },
      options.onDiagnostic,
    )
    return false
  }
}

/** The questions that should be validated for *answers*, conditions applied. */
export function applicableQuestions(
  plan: QuestionnairePlan,
  answers: Record<string, unknown>,
  options: BuildOptions = {},
): QuestionPlan[] {
  const applicable: QuestionPlan[] = []
  for (const page of plan.pages as PagePlan[]) {
    if (!isApplicable(page.condition, answers, options)) continue
    for (const section of page.sections) {
      if (!isApplicable(section.condition, answers, options)) continue
      for (const question of section.questions) {
        if (isApplicable(question.condition, answers, options)) applicable.push(question)
      }
    }
  }
  return applicable
}

/**
 * The answers as they will stand once *payload* is pushed.
 *
 * The server merges the same three layers in the same order before it decides
 * what a page is asking, so a condition reading an answer from an earlier page
 * sees it here too.
 */
export function submissionDocument(
  payload: Record<string, unknown>,
  options: BuildOptions = {},
): Record<string, unknown> {
  return { ...(options.answers ?? {}), ...payload }
}

/** The questions one page is asking, given the answers so far. */
export function applicablePageQuestions(
  page: PagePlan,
  answers: Record<string, unknown>,
  options: BuildOptions = {},
): QuestionPlan[] {
  if (!isApplicable(page.condition, answers, options)) return []
  return page.sections
    .filter((section) => isApplicable(section.condition, answers, options))
    .flatMap((section) =>
      section.questions.filter((question) =>
        isApplicable(question.condition, answers, options),
      ),
    )
}

/**
 * Validate one page's payload, the way `submit_page` does on the server.
 *
 * Pass the answers already recorded as `options.answers`: what the page is
 * asking is decided against the answers as they will be once this page lands,
 * not as they were before it.
 */
export function validatePage(
  page: PagePlan,
  payload: Record<string, unknown>,
  options: BuildOptions = {},
): AnswerIssue[] {
  const document = submissionDocument(payload, options)
  const issues: AnswerIssue[] = []
  for (const question of applicablePageQuestions(page, document, options)) {
    issues.push(
      ...validateQuestion(question, payload[question.key], document, [question.key], {
        ...options,
        answers: document,
      }),
    )
  }
  return issues
}

/** A Zod schema for one page's payload, for the form on that page. */
export function buildPageSchema(page: PagePlan, options: BuildOptions = {}): z.ZodType {
  return z.record(z.string(), z.unknown()).superRefine((payload, ctx) => {
    for (const issue of validatePage(page, payload, options)) {
      ctx.addIssue({
        code: "custom",
        message: issue.message,
        path: issue.path,
        params: { validator: issue.validator, errorKey: issue.errorKey },
      })
    }
  })
}

/** Validate a whole answer set, skipping what the conditions rule out. */
export function validateAnswers(
  plan: QuestionnairePlan,
  answers: Record<string, unknown>,
  options: BuildOptions = {},
): AnswerIssue[] {
  const issues: AnswerIssue[] = []
  for (const question of applicableQuestions(plan, answers, options)) {
    issues.push(
      ...validateQuestion(question, answers[question.key], answers, [question.key], options),
    )
  }
  return issues
}

function validateQuestion(
  plan: QuestionPlan,
  value: unknown,
  answers: Record<string, unknown>,
  path: (string | number)[],
  options: BuildOptions,
): AnswerIssue[] {
  const issues = validateAnswer(plan, value, { ...options, answers }).map((issue) => ({
    ...issue,
    path: [...path, ...issue.path],
  }))
  const sub = plan.subQuestionnaire
  if (!isExpandedSubQuestionnaire(sub)) return issues
  if (plan.type === "sub_questionnaire_list" && Array.isArray(value)) {
    value.forEach((entry, index) => {
      issues.push(...nestedIssues(sub, entry, [...path, index], options))
    })
  } else if (plan.type === "sub_questionnaire" && value && typeof value === "object") {
    issues.push(...nestedIssues(sub, value, path, options))
  }
  return issues
}

function nestedIssues(
  sub: QuestionnairePlan,
  value: unknown,
  path: (string | number)[],
  options: BuildOptions,
): AnswerIssue[] {
  const nested = (value ?? {}) as Record<string, unknown>
  return validateAnswers(sub, nested, options).map((issue) => ({
    ...issue,
    path: [...path, ...issue.path],
  }))
}

/** A Zod schema for a whole questionnaire's answers. */
export function buildQuestionnaireSchema(
  plan: QuestionnairePlan,
  options: BuildOptions = {},
): z.ZodType {
  if (plan.planVersion !== SUPPORTED_PLAN_VERSION) {
    report(
      {
        code: "plan-version",
        message:
          `This plan is version ${plan.planVersion}, and this client understands ` +
          `version ${SUPPORTED_PLAN_VERSION}. Some rules may not be checked in the browser.`,
      },
      options.onDiagnostic,
    )
  }
  return z.record(z.string(), z.unknown()).superRefine((answers, ctx) => {
    for (const issue of validateAnswers(plan, answers, options)) {
      ctx.addIssue({
        code: "custom",
        message: issue.message,
        path: issue.path,
        params: { validator: issue.validator, errorKey: issue.errorKey },
      })
    }
  })
}

/** The error keys carried by a Zod error, in order. */
export function errorKeysOf(error: z.ZodError): string[] {
  return error.issues.map((issue) => {
    const params = (issue as { params?: Record<string, unknown> }).params
    return typeof params?.errorKey === "string" ? params.errorKey : issue.code
  })
}
