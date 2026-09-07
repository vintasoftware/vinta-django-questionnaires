// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, within } from "@testing-library/react"
import { useState } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"

import type { EditorCatalog, QuestionnaireDefinition } from "../src/definition.js"
import { planFromDefinition } from "../src/preview.js"
import type { QuestionPlan, QuestionnairePlan } from "../src/plan.js"
import {
  QuestionnaireView,
  columnsFor,
  packRows,
  rangeForWidth,
  registerWidget,
  widthOf,
  resetWidgetOverrides,
  resolveWidget,
  spanOf,
} from "../src/widgets/index.js"

afterEach(() => {
  cleanup()
  resetWidgetOverrides()
})

// ------------------------------------------------------------------ fixtures

function question(overrides: Partial<QuestionPlan> = {}): QuestionPlan {
  return {
    key: "name",
    type: "free_text",
    title: "Your name",
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

function plan(questions: QuestionPlan[], overrides: Partial<QuestionnairePlan> = {}) {
  return {
    planVersion: 1,
    questionnaire: "intake",
    version: 1,
    title: "Intake",
    description: "",
    windowSizeRanges: [
      { key: "mobile", label: "Phone", minWidth: 0, maxWidth: 767 },
      { key: "desktop", label: "Desktop", minWidth: 768, maxWidth: null },
    ],
    columns: { mobile: 4, desktop: 12 },
    pages: [
      {
        key: "about",
        title: "About",
        description: "",
        conclusion: "",
        condition: "",
        isSkippable: false,
        columns: {},
        sections: [
          {
            key: "basics",
            title: "Basics",
            description: "",
            conclusion: "",
            defaultState: "open" as const,
            condition: "",
            columns: {},
            questions,
          },
        ],
      },
    ],
    ...overrides,
  }
}

function view(questions: QuestionPlan[], props: Record<string, unknown> = {}) {
  const onChange = vi.fn()
  render(
    <QuestionnaireView
      plan={plan(questions)}
      answers={{}}
      onChange={onChange}
      rangeKey="desktop"
      {...props}
    />,
  )
  return onChange
}

// -------------------------------------------------------------------- grid

describe("the grid", () => {
  it("takes the innermost layer that declares a count", () => {
    expect(columnsFor([{ desktop: 12 }, { desktop: 6 }, undefined], "desktop")).toBe(6)
    expect(columnsFor([{ desktop: 12 }, undefined, undefined], "desktop")).toBe(12)
  })

  it("falls back to the default when nobody declares one", () => {
    expect(columnsFor([{}, {}], "desktop")).toBe(12)
  })

  it("never lets a question be wider than the grid it sits in", () => {
    expect(spanOf(question({ minimumColumns: { mobile: 8 } }), "mobile", 4)).toBe(4)
  })

  it("packs questions until the row is full", () => {
    const six = () => question({ minimumColumns: { desktop: 6 } })
    const rows = packRows([six(), six(), six()], "desktop", 12)

    expect(rows).toHaveLength(2)
    expect(rows[0]?.items).toHaveLength(2)
    expect(rows[1]?.items).toHaveLength(1)
  })

  it("opens a row for a question that must be first in one", () => {
    const rows = packRows(
      [
        question({ minimumColumns: { desktop: 6 } }),
        question({ minimumColumns: { desktop: 6 }, requiresBeingFirstInARow: true }),
      ],
      "desktop",
      12,
    )

    expect(rows).toHaveLength(2)
  })

  it("closes the row a question that must be last lands in", () => {
    const rows = packRows(
      [
        question({ minimumColumns: { desktop: 4 }, requiresBeingLastInARow: true }),
        question({ minimumColumns: { desktop: 4 } }),
      ],
      "desktop",
      12,
    )

    expect(rows).toHaveLength(2)
    expect(rows[0]?.items).toHaveLength(1)
  })

  it("finds the range a width falls in", () => {
    const ranges = plan([]).windowSizeRanges
    expect(rangeForWidth(ranges, 375)?.key).toBe("mobile")
    expect(rangeForWidth(ranges, 1440)?.key).toBe("desktop")
  })
})

describe("the width a range previews at", () => {
  const phone = { key: "mobile", label: "Phone", minWidth: 0, maxWidth: 767 }
  const tablet = { key: "tablet", label: "Tablet", minWidth: 768, maxWidth: 1023 }
  const desktop = { key: "desktop", label: "Desktop", minWidth: 1024, maxWidth: null }

  it("takes the middle of a bounded range", () => {
    expect(widthOf(phone)).toBe(384)
    expect(widthOf(tablet)).toBe(896)
  })

  it("clears the floor of an unbounded one", () => {
    // Not 1024: that is the boundary it shares with the range below, the one
    // width at which a desktop preview looks exactly like a tablet preview.
    expect(widthOf(desktop)).toBe(1280)
  })

  it("never gives two neighbours the same width", () => {
    // The bug this replaced: every range rendered at its widest point, so the
    // widest tablet was a pixel off the narrowest desktop.
    const widths = [phone, tablet, desktop].map((range) => widthOf(range))
    expect(new Set(widths).size).toBe(widths.length)
    expect(widths[0]).toBeLessThan(widths[1]!)
    expect(widths[1]).toBeLessThan(widths[2]!)
  })

  it("stays wide enough to render at all", () => {
    expect(widthOf({ key: "tiny", label: "", minWidth: 0, maxWidth: 100 })).toBe(320)
  })

  it("falls back for a single unbounded range starting at zero", () => {
    expect(widthOf({ key: "any", label: "", minWidth: 0, maxWidth: null })).toBe(1280)
  })

  it("falls back when there is no range at all", () => {
    expect(widthOf(undefined)).toBe(1280)
  })
})

// ---------------------------------------------------------------- registry

describe("the widget registry", () => {
  it("renders a question type with no widget resolved", () => {
    view([question()])
    expect(screen.getByLabelText("Your name")).toBeTruthy()
  })

  it("prefers the widget the plan names over the question type", () => {
    const found = resolveWidget(question({ type: "free_text", widget: "textarea" }))
    const fallback = resolveWidget(question({ type: "free_text" }))
    expect(found).not.toBe(fallback)
  })

  it("lets a host take a key over, and hands it back on unregister", () => {
    const mine = () => <output data-testid="mine">mine</output>
    const shipped = resolveWidget(question({ widget: "textarea" }))

    registerWidget("textarea", mine)
    expect(resolveWidget(question({ widget: "textarea" }))).toBe(mine)

    resetWidgetOverrides()
    expect(resolveWidget(question({ widget: "textarea" }))).toBe(shipped)
  })

  it("says so rather than skipping a question nothing renders", () => {
    view([question({ type: "invented", widget: "invented" })])
    expect(screen.getByText(/Nothing renders/)).toBeTruthy()
  })
})

// ----------------------------------------------------------------- widgets

describe("the default widgets", () => {
  it("reports what was typed into a text question", () => {
    const onChange = view([question()])
    fireEvent.change(screen.getByLabelText("Your name"), { target: { value: "Ada" } })
    expect(onChange).toHaveBeenCalledWith("name", "Ada")
  })

  it("reports a number as a number, and an empty field as null", () => {
    // Stateful, because clearing a controlled field only reaches `onChange` if
    // the value it is being cleared from actually made it back in.
    const seen: unknown[] = []
    function Host() {
      const [answers, setAnswers] = useState<Record<string, unknown>>({})
      return (
        <QuestionnaireView
          plan={plan([question({ key: "age", type: "number", title: "Age" })])}
          answers={answers}
          rangeKey="desktop"
          onChange={(key, value) => {
            seen.push(value)
            setAnswers((current) => ({ ...current, [key]: value }))
          }}
        />
      )
    }
    render(<Host />)
    const field = screen.getByLabelText("Age")

    fireEvent.change(field, { target: { value: "41" } })
    fireEvent.change(field, { target: { value: "" } })

    expect(seen).toEqual([41, null])
  })

  it("stores what was typed into the other box, not a sentinel", () => {
    // A question that allows an other option is typed as a string rather than
    // an enum for exactly this reason: the answer is the words, not a marker.
    const onChange = view([
      question({
        key: "how",
        type: "single_choice",
        title: "How did you hear about us?",
        allowsOther: true,
        otherLabel: "Some other way",
        choices: [{ value: "search", label: "Search" }],
      }),
    ])

    fireEvent.click(screen.getByRole("radio", { name: "Some other way" }))
    fireEvent.change(screen.getByRole("textbox", { name: "Some other way" }), {
      target: { value: "A friend" },
    })

    expect(onChange).toHaveBeenLastCalledWith("how", "A friend")
  })

  it("collects a multiple choice answer as a list", () => {
    const onChange = view([
      question({
        key: "langs",
        type: "multiple_choice",
        title: "Languages",
        choices: [
          { value: "py", label: "Python" },
          { value: "ts", label: "TypeScript" },
        ],
      }),
    ])

    fireEvent.click(screen.getByLabelText("Python"))
    expect(onChange).toHaveBeenCalledWith("langs", ["py"])
  })

  it("keeps a range's two edges in one answer", () => {
    const onChange = view([question({ key: "when", type: "date_range", title: "When" })])
    fireEvent.change(screen.getByLabelText("From"), { target: { value: "2026-01-01" } })
    expect(onChange).toHaveBeenCalledWith("when", { start: "2026-01-01" })
  })

  it("keys a matrix answer by row", () => {
    const onChange = view([
      question({
        key: "grid",
        type: "binary_matrix",
        title: "Availability",
        matrix: {
          rows: [{ value: "mon", label: "Monday" }],
          columns: [{ value: "am", label: "Morning" }],
        },
      }),
    ])

    fireEvent.click(screen.getByLabelText("Monday / Morning"))
    expect(onChange).toHaveBeenCalledWith("grid", { mon: ["am"] })
  })
})

// ------------------------------------------------------------------- view

describe("the rendered questionnaire", () => {
  it("lays a question out on the columns it asks for", () => {
    view([question({ minimumColumns: { desktop: 6 } })])
    const cell = globalThis.document.querySelector(".vqf-cell")
    expect(cell?.getAttribute("data-span")).toBe("6")
  })

  it("clamps a question to the grid of the range in force", () => {
    view([question({ minimumColumns: { mobile: 8, desktop: 8 } })], { rangeKey: "mobile" })
    // The questionnaire declares four columns on a phone, so eight is four.
    expect(globalThis.document.querySelector(".vqf-cell")?.getAttribute("data-span")).toBe("4")
  })

  it("marks a required question", () => {
    view([
      question({
        checks: [
          {
            kind: "custom",
            validator: "required",
            params: {},
            messages: {},
            serverOnly: false,
            skipWhenEmpty: false,
          },
        ],
      }),
    ])
    expect(screen.getByTitle("Required")).toBeTruthy()
  })

  it("shows what failed against the question that failed", () => {
    view([question()], { errors: { name: ["Tell us your name."] } })
    expect(screen.getByText("Tell us your name.")).toBeTruthy()
  })

  it("says whatever the catalogue passed in says", () => {
    view([question({ key: "when", type: "date_range", title: "When" })], {
      strings: { "widget.range.start": "De" },
    })
    expect(screen.getByLabelText("De")).toBeTruthy()
  })
})

// ---------------------------------------------------------------- preview

describe("a definition as a plan", () => {
  const catalog: EditorCatalog = {
    catalogVersion: 1,
    defaultColumnCount: 12,
    questionTypes: [
      {
        key: "single_choice",
        label: "Single choice",
        answerShape: "scalar",
        supportsChoices: true,
        supportsValueSet: false,
        supportsOtherOption: true,
        usesMatrixAxes: false,
        requiresItemType: false,
        requiresSubQuestionnaire: false,
      },
    ],
    scalarQuestionTypes: ["single_choice"],
    validators: [],
    widgets: [
      {
        key: "radio-group",
        name: "Radio group",
        description: "",
        component: "radio-group",
        propsSchema: {},
        defaultProps: { orientation: "vertical" },
        questionTypes: ["single_choice"],
        defaultForQuestionTypes: ["single_choice"],
      },
    ],
    valueSets: [],
    questionnaires: [],
    choiceAxes: [],
    sectionStates: [],
    versionStatuses: [],
    editPolicies: [],
  }

  function definition(): QuestionnaireDefinition {
    return {
      documentVersion: 1,
      questionnaire: { key: "intake", name: "Intake" },
      version: 1,
      title: "Intake",
      description: "",
      status: "draft",
      editPolicy: "always",
      responsesDueAt: null,
      editsDueAt: null,
      windowSizeRanges: [{ key: "desktop", label: "Desktop", minWidth: 0, maxWidth: null }],
      columns: { desktop: 12 },
      pages: [
        {
          key: "about",
          title: "About",
          description: "",
          conclusion: "",
          condition: "",
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
                {
                  key: "how",
                  title: "How did you hear about us?",
                  description: "",
                  questionType: "single_choice",
                  itemQuestionType: "",
                  condition: "",
                  requiresBeingFirstInARow: false,
                  requiresBeingLastInARow: false,
                  minimumColumns: { desktop: 6 },
                  widget: null,
                  widgetProps: {},
                  allowsOther: true,
                  otherLabel: "Some other way",
                  valueSet: null,
                  subQuestionnaire: null,
                  subQuestionnaireVersion: null,
                  choices: [
                    {
                      axis: "option",
                      value: "search",
                      label: "Search",
                      extra: {},
                      isActive: true,
                    },
                    { axis: "option", value: "old", label: "Gone", extra: {}, isActive: false },
                  ],
                  validators: [],
                },
              ],
            },
          ],
        },
      ],
    }
  }

  it("resolves the widget a question type defaults to", () => {
    const resolved = planFromDefinition(definition(), catalog)
    const [first] = resolved.pages[0]!.sections[0]!.questions
    expect(first?.widget).toBe("radio-group")
    expect(first?.widgetProps).toEqual({ orientation: "vertical" })
  })

  it("leaves out the choices an author turned off", () => {
    const resolved = planFromDefinition(definition(), catalog)
    expect(resolved.pages[0]!.sections[0]!.questions[0]?.choices).toEqual([
      { value: "search", label: "Search" },
    ])
  })

  it("carries the other label through, which the plan used to drop", () => {
    const resolved = planFromDefinition(definition(), catalog)
    expect(resolved.pages[0]!.sections[0]!.questions[0]?.otherLabel).toBe("Some other way")
  })

  it("renders without a catalog, which is what an unloaded editor has", () => {
    const resolved = planFromDefinition(definition(), null)
    render(
      <QuestionnaireView plan={resolved} answers={{}} onChange={() => {}} rangeKey="desktop" />,
    )
    expect(screen.getByText("How did you hear about us?")).toBeTruthy()
  })

  it("keeps the widths an author set", () => {
    const resolved = planFromDefinition(definition(), catalog)
    render(
      <QuestionnaireView plan={resolved} answers={{}} onChange={() => {}} rangeKey="desktop" />,
    )
    const section = globalThis.document.querySelector(".vqf-grid")
    expect(section?.getAttribute("data-columns")).toBe("12")
    expect(within(section as HTMLElement).getByText("How did you hear about us?")).toBeTruthy()
    expect(globalThis.document.querySelector(".vqf-cell")?.getAttribute("data-span")).toBe("6")
  })
})
