/**
 * The corpus the server writes, replayed against the schemas this package builds.
 *
 * Every case here also runs in the Python suite, against the validator that
 * emitted it.  Two implementations, one set of expectations: when they drift,
 * this file is what says so.
 */

import { readFileSync } from "node:fs"
import { describe, expect, it } from "vitest"

import { buildQuestionSchema, errorKeysOf } from "../src/build.js"
import { hasCheck } from "../src/checks.js"
import { isCustomCheck, type QuestionPlan } from "../src/plan.js"

interface ConformanceCase {
  validator: string
  label: string
  questionType: string
  params: Record<string, unknown>
  value: unknown
  expects: string[]
  plan: QuestionPlan
}

const corpus = JSON.parse(
  readFileSync(new URL("../../shared/conformance-cases.json", import.meta.url), "utf8"),
) as { planVersion: number; cases: ConformanceCase[] }

const manifest = JSON.parse(
  readFileSync(new URL("../../shared/validators.json", import.meta.url), "utf8"),
) as {
  validators: {
    key: string
    client: { mode: string; checks: { kind: string }[] }
  }[]
}

describe("conformance with the server", () => {
  for (const [index, testCase] of corpus.cases.entries()) {
    const name = [testCase.validator, index, testCase.label].filter(Boolean).join(" ")
    it(name, () => {
      const result = buildQuestionSchema(testCase.plan).safeParse(testCase.value)
      const errorKeys = result.success ? [] : errorKeysOf(result.error)

      expect(errorKeys).toEqual(testCase.expects)
    })
  }
})

describe("the manifest", () => {
  it("names no check this build cannot apply", () => {
    const missing = manifest.validators
      .filter((validator) => validator.client.mode === "checks")
      .flatMap((validator) => validator.client.checks.map((check) => check.kind))
      .filter((kind) => !hasCheck(kind))

    expect(missing).toEqual([])
  })

  it("covers every case in the corpus", () => {
    const withoutChecks = corpus.cases.filter((testCase) => testCase.plan.checks.length === 0)

    expect(withoutChecks).toEqual([])
  })

  it("has no built-in that needs a client implementation", () => {
    const custom = corpus.cases.filter((testCase) => testCase.plan.checks.some(isCustomCheck))

    expect(custom.map((testCase) => testCase.validator)).toEqual([])
  })
})
