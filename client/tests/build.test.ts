import { beforeEach, describe, expect, it, vi } from "vitest"

import {
  applicablePageQuestions,
  applicableQuestions,
  buildPageSchema,
  buildQuestionSchema,
  buildQuestionnaireSchema,
  errorKeysOf,
  validateAnswers,
  validatePage,
} from "../src/build.js"
import {
  onDiagnostic,
  resetDiagnostics,
  setFallbackReporter,
  type Diagnostic,
} from "../src/diagnostics.js"
import { formatMessage } from "../src/message.js"
import type { PagePlan, QuestionPlan, QuestionnairePlan } from "../src/plan.js"
import { registerClientValidator, unregisterClientValidator } from "../src/registry.js"

function requiredCheck() {
  return {
    kind: "presence.required",
    validator: "required",
    errorKey: "required",
    args: [],
    params: {},
    message: "This answer is required.",
    skipWhenEmpty: false,
  }
}

function page(overrides: Partial<PagePlan> = {}): PagePlan {
  return {
    key: "about",
    title: "About",
    description: "",
    conclusion: "",
    condition: "",
    isSkippable: false,
    columns: {},
    sections: [],
    ...overrides,
  }
}

function question(overrides: Partial<QuestionPlan> = {}): QuestionPlan {
  return {
    key: "answer",
    type: "free_text",
    title: "An answer",
    description: "",
    condition: "",
    checks: [],
    usesContext: false,
    widget: null,
    widgetProps: {},
    minimumColumns: {},
    requiresBeingFirstInARow: false,
    requiresBeingLastInARow: false,
    ...overrides,
  }
}

function nativeCheck(overrides: Record<string, unknown> = {}) {
  return {
    kind: "string.min",
    validator: "min_length",
    errorKey: "too_short",
    args: [3],
    params: { minimum: 3 },
    message: "Use at least {minimum} characters.",
    skipWhenEmpty: true,
    ...overrides,
  }
}

beforeEach(() => {
  resetDiagnostics()
  setFallbackReporter(null)
})

describe("messages", () => {
  it("interpolates the params the server sent", () => {
    const schema = buildQuestionSchema(question({ checks: [nativeCheck()] }))
    const result = schema.safeParse("ab")

    expect(result.success).toBe(false)
    if (!result.success) {
      expect(result.error.issues[0]?.message).toBe("Use at least 3 characters.")
    }
  })

  it("leaves a template alone when a placeholder has no value, as Python does", () => {
    expect(formatMessage("{name} is over {max_bytes}", { max_bytes: 10 })).toBe(
      "{name} is over {max_bytes}",
    )
  })

  it("fills placeholders only the failure knows", () => {
    const schema = buildQuestionSchema(
      question({
        type: "single_file",
        checks: [
          nativeCheck({
            kind: "file.maxSize",
            validator: "max_file_size",
            errorKey: "file_too_large",
            args: [10],
            params: { max_bytes: 10 },
            message: "{name} is over the {max_bytes} byte limit.",
          }),
        ],
      }),
    )
    const result = schema.safeParse({ name: "big.pdf", size: 99 })

    expect(result.success).toBe(false)
    if (!result.success) {
      expect(result.error.issues[0]?.message).toBe("big.pdf is over the 10 byte limit.")
    }
  })
})

describe("custom validators", () => {
  const customCheck = {
    kind: "custom" as const,
    validator: "is_company_domain",
    params: { domain: "vinta.com.br" },
    messages: { foreign_domain: "Use your {domain} address." },
    serverOnly: false,
    skipWhenEmpty: true,
  }

  it("runs the implementation the client registered", () => {
    registerClientValidator("is_company_domain", {
      validate(value, params, ctx) {
        if (typeof value === "string" && !value.endsWith(`@${params.domain}`)) {
          ctx.fail("foreign_domain")
        }
      },
    })

    const schema = buildQuestionSchema(question({ checks: [customCheck] }))

    expect(schema.safeParse("hugo@vinta.com.br").success).toBe(true)
    const result = schema.safeParse("hugo@example.com")
    expect(result.success).toBe(false)
    if (!result.success) {
      expect(errorKeysOf(result.error)).toEqual(["foreign_domain"])
      expect(result.error.issues[0]?.message).toBe("Use your vinta.com.br address.")
    }

    unregisterClientValidator("is_company_domain")
  })

  it("skips what it cannot run and hands the diagnostic to the host app", () => {
    const reported: Diagnostic[] = []
    const unsubscribe = onDiagnostic((diagnostic) => reported.push(diagnostic))

    const result = buildQuestionSchema(question({ checks: [customCheck] })).safeParse(
      "hugo@example.com",
    )

    expect(result.success).toBe(true)
    expect(reported).toHaveLength(1)
    expect(reported[0]?.code).toBe("missing-validator")
    expect(reported[0]?.validator).toBe("is_company_domain")
    unsubscribe()
  })

  it("reports a check kind this build does not know", () => {
    const onDiagnosticSpy = vi.fn()

    const result = buildQuestionSchema(
      question({ checks: [nativeCheck({ kind: "string.futureCheck" })] }),
      { onDiagnostic: onDiagnosticSpy },
    ).safeParse("ab")

    expect(result.success).toBe(true)
    expect(onDiagnosticSpy).toHaveBeenCalledOnce()
    expect(onDiagnosticSpy.mock.calls[0]?.[0].code).toBe("unknown-check")
  })

  it("leaves server-only checks to the server, without a console warning", () => {
    const reported: Diagnostic[] = []
    const unsubscribe = onDiagnostic((diagnostic) => reported.push(diagnostic))

    const result = buildQuestionSchema(
      question({ checks: [{ ...customCheck, serverOnly: true }] }),
    ).safeParse("hugo@example.com")

    expect(result.success).toBe(true)
    expect(reported[0]?.code).toBe("server-only")
    unsubscribe()
  })

  it("reports each distinct problem once, not once per keystroke", () => {
    const reported: Diagnostic[] = []
    const unsubscribe = onDiagnostic((diagnostic) => reported.push(diagnostic))
    const schema = buildQuestionSchema(question({ checks: [customCheck] }))

    schema.safeParse("a@example.com")
    schema.safeParse("ab@example.com")
    schema.safeParse("abc@example.com")

    expect(reported).toHaveLength(1)
    unsubscribe()
  })
})

describe("the chain", () => {
  it("gives a predicate what the earlier checks recorded", () => {
    const schema = buildQuestionSchema(
      question({
        usesContext: true,
        checks: [
          nativeCheck({ args: [2], params: { minimum: 2 } }),
          {
            kind: "logic.jmespath",
            validator: "jmespath_predicate",
            errorKey: "predicate_failed",
            args: ["results.min_length.data.length > `3`"],
            params: { expression: "results.min_length.data.length > `3`" },
            message: "This answer is not valid here.",
            skipWhenEmpty: true,
          },
        ],
      }),
    )

    expect(schema.safeParse("abcd").success).toBe(true)
    expect(schema.safeParse("abc").success).toBe(false)
  })

  it("gives a predicate the sibling answers", () => {
    const plan = question({
      checks: [
        {
          kind: "logic.jmespath",
          validator: "jmespath_predicate",
          errorKey: "predicate_failed",
          args: ["answers.has_company"],
          params: { expression: "answers.has_company" },
          message: "Only for companies.",
          skipWhenEmpty: true,
        },
      ],
    })

    expect(
      buildQuestionSchema(plan, { answers: { has_company: true } }).safeParse("Vinta").success,
    ).toBe(true)
    expect(
      buildQuestionSchema(plan, { answers: { has_company: false } }).safeParse("Vinta").success,
    ).toBe(false)
  })
})

describe("a whole questionnaire", () => {
  const plan: QuestionnairePlan = {
    planVersion: 1,
    questionnaire: "intake",
    version: 1,
    title: "Intake",
    description: "",
    windowSizeRanges: [],
    columns: {},
    pages: [
      {
        key: "about",
        title: "About",
        description: "",
        conclusion: "",
        condition: "role == 'staff'",
        isSkippable: false,
        columns: {},
        sections: [
          {
            key: "basics",
            title: "Basics",
            description: "",
            conclusion: "",
            defaultState: "open",
            condition: "",
            columns: {},
            questions: [
              question({ key: "name", checks: [nativeCheck()] }),
              question({ key: "badge", condition: "has_badge", checks: [nativeCheck()] }),
            ],
          },
        ],
      },
    ],
  }

  it("skips what the conditions rule out", () => {
    expect(applicableQuestions(plan, {})).toEqual([])
    expect(applicableQuestions(plan, { role: "staff" }).map((entry) => entry.key)).toEqual([
      "name",
    ])
    expect(
      applicableQuestions(plan, { role: "staff", has_badge: true }).map((entry) => entry.key),
    ).toEqual(["name", "badge"])
  })

  it("reports issues at the answering question's path", () => {
    const issues = validateAnswers(plan, { role: "staff", name: "ab" })

    expect(issues).toHaveLength(1)
    expect(issues[0]?.path).toEqual(["name"])
    expect(issues[0]?.errorKey).toBe("too_short")
  })

  it("builds a schema over the whole answer set", () => {
    const schema = buildQuestionnaireSchema(plan)

    expect(schema.safeParse({ role: "staff", name: "Hugo" }).success).toBe(true)
    const result = schema.safeParse({ role: "staff", name: "ab" })
    expect(result.success).toBe(false)
    if (!result.success) {
      expect(result.error.issues[0]?.path).toEqual(["name"])
    }
  })

  it("warns when the plan is newer than this build understands", () => {
    const onDiagnosticSpy = vi.fn()

    buildQuestionnaireSchema({ ...plan, planVersion: 99 }, { onDiagnostic: onDiagnosticSpy })

    expect(onDiagnosticSpy.mock.calls[0]?.[0].code).toBe("plan-version")
  })
})

describe("one page at a time", () => {
  const contactPage = page({
    key: "contact",
    sections: [
      {
        key: "basics",
        title: "Basics",
        description: "",
        conclusion: "",
        defaultState: "open",
        condition: "",
        columns: {},
        questions: [
          question({ key: "name", checks: [nativeCheck()] }),
          question({
            key: "company_name",
            condition: "has_company == 'yes'",
            checks: [requiredCheck()],
          }),
        ],
      },
    ],
  })

  it("asks only what the answers so far call for", () => {
    const asked = applicablePageQuestions(contactPage, { has_company: "no" })

    expect(asked.map((entry) => entry.key)).toEqual(["name"])
  })

  it("decides against the answers as they will be, not as they were", () => {
    // has_company arrives in this very payload, and already counts.
    const issues = validatePage(contactPage, { name: "Hugo", has_company: "yes" })

    expect(issues.map((issue) => issue.path)).toEqual([["company_name"]])
    expect(validatePage(contactPage, { name: "Hugo", has_company: "no" })).toEqual([])
  })

  it("takes the answers already recorded into account", () => {
    const issues = validatePage(
      contactPage,
      { name: "Hugo" },
      { answers: { has_company: "yes", company_name: "Vinta" } },
    )

    // company_name is asked, and this payload does not carry it.
    expect(issues.map((issue) => issue.path)).toEqual([["company_name"]])
  })

  it("builds a schema for the form on that page", () => {
    const schema = buildPageSchema(contactPage)

    expect(schema.safeParse({ name: "Hugo", has_company: "no" }).success).toBe(true)
    const result = schema.safeParse({ name: "ab", has_company: "no" })
    expect(result.success).toBe(false)
    if (!result.success) {
      expect(result.error.issues[0]?.path).toEqual(["name"])
    }
  })

  it("says nothing about a page whose own condition does not hold", () => {
    const conditional = page({ ...contactPage, condition: "role == 'staff'" })

    expect(validatePage(conditional, { name: "" })).toEqual([])
  })
})
