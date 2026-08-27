/**
 * The base Zod type of a question, decided by its type alone.
 *
 * Keeping this separate from the checks is what keeps the whole thing small:
 * a closed set of question types written once here, and everything a
 * questionnaire author configures arrives as checks on top.
 */

import { z } from "zod"

import type { ChoicePlan, QuestionPlan } from "./plan.js"

const fileType = z
  .object({
    name: z.string().optional(),
    size: z.number().optional(),
    content_type: z.string().optional(),
  })
  .catchall(z.unknown())

const rangeType = z.object({ start: z.unknown(), end: z.unknown() }).catchall(z.unknown())

const answerSet = z.record(z.string(), z.unknown())

function enumOf(choices: ChoicePlan[]): z.ZodType {
  const values = choices.map((choice) => choice.value)
  return z.enum(values as [string, ...string[]])
}

export function baseTypeFor(plan: QuestionPlan): z.ZodType {
  switch (plan.type) {
    case "single_choice":
    case "single_select":
      return plan.choices?.length && !plan.allowsOther ? enumOf(plan.choices) : z.string()
    case "multiple_choice":
    case "multi_select":
      return z.array(
        plan.choices?.length && !plan.allowsOther ? enumOf(plan.choices) : z.string(),
      )
    case "free_text":
    case "url":
    case "time":
    case "date":
    case "date_time":
    case "month":
      return z.string()
    case "number":
    case "year":
    case "time_duration":
      return z.number()
    case "number_range":
    case "date_range":
    case "date_time_range":
      return rangeType
    case "single_file":
      return fileType
    case "multiple_files":
      return z.array(fileType)
    case "binary_matrix":
      return z.record(z.string(), z.array(z.string()))
    case "item_list":
      return z.array(plan.itemType ? baseTypeForQuestionType(plan.itemType) : z.unknown())
    case "sub_questionnaire":
      return answerSet
    case "sub_questionnaire_list":
      return z.array(answerSet)
    default:
      return z.unknown()
  }
}

function baseTypeForQuestionType(type: string): z.ZodType {
  return baseTypeFor({
    key: "",
    type,
    title: "",
    description: "",
    condition: "",
    checks: [],
    usesContext: false,
    widget: null,
    widgetProps: {},
    minimumColumns: {},
    requiresBeingFirstInARow: false,
    requiresBeingLastInARow: false,
  })
}
