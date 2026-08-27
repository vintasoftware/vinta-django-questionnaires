import { describe, expect, it } from "vitest"

import type {
  DefinitionIssue,
  EditorCatalog,
  QuestionnaireDefinition,
} from "../src/definition.js"
import {
  allQuestions,
  editorReducer,
  initialState,
  isDirty,
  issuesAt,
  hasIssuesUnder,
  newQuestion,
  orphanedQuestionKeys,
  outgoingDocument,
  pathOf,
  questionAt,
  slugify,
  summariseIssues,
  uniqueKey,
  validateDefinition,
  type EditorAction,
  type EditorState,
} from "../src/editorState.js"

function document(): QuestionnaireDefinition {
  return {
    documentVersion: 1,
    questionnaire: { key: "intake", name: "Intake" },
    version: 1,
    title: "Intake form",
    description: "",
    status: "draft",
    editPolicy: "always",
    responsesDueAt: null,
    editsDueAt: null,
    windowSizeRanges: [
      { key: "mobile", label: "Mobile", minWidth: 0, maxWidth: 767 },
      { key: "desktop", label: "Desktop", minWidth: 768, maxWidth: null },
    ],
    columns: { mobile: 4 },
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
                ...newQuestion([], "single_choice"),
                key: "flavour",
                title: "Favourite flavour",
                choices: [
                  {
                    axis: "option",
                    value: "vanilla",
                    label: "Vanilla",
                    extra: {},
                    isActive: true,
                  },
                  { axis: "option", value: "salt", label: "Salted", extra: {}, isActive: true },
                ],
                validators: [
                  { validator: "required", params: {}, messageOverrides: {}, isEnabled: true },
                  {
                    validator: "one_of",
                    params: { values: ["vanilla"] },
                    messageOverrides: {},
                    isEnabled: true,
                  },
                ],
              },
            ],
          },
        ],
      },
    ],
  }
}

const catalog: EditorCatalog = {
  catalogVersion: 1,
  defaultColumnCount: 12,
  questionTypes: [
    {
      key: "free_text",
      label: "Free text",
      answerShape: "scalar",
      supportsChoices: false,
      supportsValueSet: false,
      supportsOtherOption: false,
      usesMatrixAxes: false,
      requiresItemType: false,
      requiresSubQuestionnaire: false,
    },
    {
      key: "single_choice",
      label: "Single choice",
      answerShape: "scalar",
      supportsChoices: true,
      supportsValueSet: true,
      supportsOtherOption: true,
      usesMatrixAxes: false,
      requiresItemType: false,
      requiresSubQuestionnaire: false,
    },
    {
      key: "item_list",
      label: "List of items",
      answerShape: "list",
      supportsChoices: false,
      supportsValueSet: false,
      supportsOtherOption: false,
      usesMatrixAxes: false,
      requiresItemType: true,
      requiresSubQuestionnaire: false,
    },
  ],
  scalarQuestionTypes: ["free_text", "single_choice"],
  validators: [
    {
      key: "required",
      label: "Required",
      description: "An answer is required.",
      paramsSchema: { type: "object", properties: {} },
      errorKeys: [{ key: "required", message: "This is required." }],
      questionTypes: null,
      clientMode: "checks",
      skipWhenEmpty: false,
      readsContext: false,
    },
    {
      key: "min_length",
      label: "Minimum length",
      description: "Not shorter than.",
      paramsSchema: {
        type: "object",
        properties: { minimum: { type: "integer" } },
        required: ["minimum"],
      },
      errorKeys: [{ key: "too_short", message: "Too short." }],
      questionTypes: ["free_text"],
      clientMode: "checks",
      skipWhenEmpty: true,
      readsContext: false,
    },
    {
      key: "one_of",
      label: "Allowed values",
      description: "One of the allowed values.",
      paramsSchema: { type: "object", properties: { values: { type: "array" } } },
      errorKeys: [{ key: "not_allowed", message: "Not allowed." }],
      questionTypes: ["single_choice"],
      clientMode: "checks",
      skipWhenEmpty: true,
      readsContext: false,
    },
  ],
  widgets: [],
  valueSets: [],
  questionnaires: [],
  choiceAxes: [{ value: "option", label: "Option" }],
  sectionStates: [{ value: "open", label: "Open" }],
  versionStatuses: [{ value: "draft", label: "Draft" }],
  editPolicies: [{ value: "always", label: "Always" }],
}

const run = (actions: EditorAction[], from: EditorState = initialState(document())) =>
  actions.reduce(editorReducer, from)

// ------------------------------------------------------------------- paths

describe("paths", () => {
  it("addresses a node the way the server does", () => {
    expect(pathOf({ kind: "version" })).toBe("")
    expect(pathOf({ page: 1 })).toBe("pages.1")
    expect(pathOf({ page: 1, section: 0 })).toBe("pages.1.sections.0")
    expect(pathOf({ page: 1, section: 0, question: 2 })).toBe("pages.1.sections.0.questions.2")
  })

  it("collects the issues of one node and flags its ancestors", () => {
    const issues: DefinitionIssue[] = [
      {
        path: "pages.0.sections.0.questions.0",
        errors: { key: ["Taken."], title: ["Empty."] },
      },
      { path: "pages.0.sections.0.questions.0", errors: { key: ["Also bad."] } },
      { path: "pages.1", errors: { key: ["Nope."] } },
    ]

    expect(issuesAt(issues, "pages.0.sections.0.questions.0")).toEqual({
      key: ["Taken.", "Also bad."],
      title: ["Empty."],
    })
    expect(hasIssuesUnder(issues, "pages.0")).toBe(true)
    expect(hasIssuesUnder(issues, "pages.2")).toBe(false)
  })
})

// ------------------------------------------------------------------ editing

describe("editing the tree", () => {
  it("adds a page with a key nothing else uses", () => {
    const state = run([
      { type: "insert", path: null },
      { type: "insert", path: null },
    ])

    expect(state.document.pages.map((page) => page.key)).toEqual(["about", "page", "page-2"])
  })

  it("adds a question keyed uniquely across the whole version", () => {
    const state = run([
      { type: "insert", path: { page: 0 } },
      { type: "insert", path: { page: 0, section: 0 } },
      { type: "insert", path: { page: 0, section: 1 } },
    ])

    const keys = allQuestions(state.document).map(({ question }) => question.key)
    expect(keys).toEqual(["flavour", "question", "question-2"])
  })

  it("patches only the node addressed", () => {
    const state = run([
      {
        type: "patch",
        path: { page: 0, section: 0, question: 0 },
        patch: { title: "Flavour?" },
      },
    ])

    expect(questionAt(state.document, { page: 0, section: 0, question: 0 })?.title).toBe(
      "Flavour?",
    )
    expect(state.document.pages[0]?.title).toBe("About")
  })

  it("reorders, and refuses to reorder past the ends", () => {
    const twoPages = run([{ type: "insert", path: null }])
    expect(
      run([{ type: "move", path: { page: 1 }, by: -1 }], twoPages).document.pages[0]?.key,
    ).toBe("page")
    expect(
      run([{ type: "move", path: { page: 0 }, by: -1 }], twoPages).document.pages[0]?.key,
    ).toBe("about")
  })

  it("reorders a list by index, which is what a drag gives it", () => {
    const state = run([
      { type: "insert", path: null },
      { type: "insert", path: null },
      { type: "reorder", path: null, from: 2, to: 0 },
    ])

    expect(state.document.pages.map((page) => page.key)).toEqual(["page-2", "about", "page"])
  })

  it("reorders questions within their own section", () => {
    const state = run([
      { type: "insert", path: { page: 0, section: 0 } },
      { type: "reorder", path: { page: 0, section: 0 }, from: 1, to: 0 },
    ])

    expect(
      state.document.pages[0]?.sections[0]?.questions.map((question) => question.key),
    ).toEqual(["question", "flavour"])
  })

  it("ignores a reorder that goes nowhere or off the end", () => {
    const before = initialState(document())
    for (const action of [
      { type: "reorder", path: null, from: 0, to: 0 },
      { type: "reorder", path: null, from: 0, to: 5 },
      { type: "reorder", path: null, from: -1, to: 0 },
    ] as EditorAction[]) {
      expect(editorReducer(before, action).document.pages.map((page) => page.key)).toEqual([
        "about",
      ])
    }
  })

  it("keeps the selection on what was selected when its container is reordered", () => {
    const state = run([
      { type: "insert", path: null },
      { type: "select", selection: { kind: "page", page: 0 } },
      { type: "reorder", path: null, from: 0, to: 1 },
    ])

    expect(state.selection).toEqual({ kind: "page", page: 1 })
  })

  it("follows a question selection when the page it is on moves", () => {
    const state = run([
      { type: "insert", path: null },
      { type: "select", selection: { kind: "question", page: 0, section: 0, question: 0 } },
      { type: "reorder", path: null, from: 0, to: 1 },
    ])

    expect(state.selection).toEqual({
      kind: "question",
      page: 1,
      section: 0,
      question: 0,
    })
  })

  it("leaves a selection in another page alone when this page reorders its sections", () => {
    const state = run([
      { type: "insert", path: null },
      { type: "select", selection: { kind: "section", page: 0, section: 0 } },
      { type: "reorder", path: { page: 1 }, from: 0, to: 0 },
    ])

    expect(state.selection).toEqual({ kind: "section", page: 0, section: 0 })
  })

  it("moves the selection up a level when what was selected is deleted", () => {
    const state = run([
      { type: "select", selection: { kind: "question", page: 0, section: 0, question: 0 } },
      { type: "remove", path: { page: 0, section: 0, question: 0 } },
    ])

    expect(state.selection).toEqual({ kind: "section", page: 0, section: 0 })
  })

  it("leaves a selection that is not under what was deleted alone", () => {
    const state = run([
      { type: "insert", path: null },
      { type: "select", selection: { kind: "page", page: 0 } },
      { type: "remove", path: { page: 1 } },
    ])

    expect(state.selection).toEqual({ kind: "page", page: 0 })
  })
})

describe("choices and validators", () => {
  const path = { page: 0, section: 0, question: 0 }

  it("patches one entry of a list", () => {
    const state = run([
      { type: "patchItem", path, list: "choices", index: 0, patch: { label: "Plain" } },
    ])

    expect(questionAt(state.document, path)?.choices[0]?.label).toBe("Plain")
    expect(questionAt(state.document, path)?.choices[1]?.label).toBe("Salted")
  })

  it("reorders the validator chain by index, which is what a drag gives it", () => {
    const state = run([{ type: "reorderItem", path, list: "validators", from: 0, to: 1 }])

    expect(questionAt(state.document, path)?.validators.map((one) => one.validator)).toEqual([
      "one_of",
      "required",
    ])
  })

  it("reorders the validator chain", () => {
    const state = run([{ type: "moveItem", path, list: "validators", index: 0, by: 1 }])

    expect(questionAt(state.document, path)?.validators.map((one) => one.validator)).toEqual([
      "one_of",
      "required",
    ])
  })

  it("removes an entry without touching the other list", () => {
    const state = run([{ type: "removeItem", path, list: "validators", index: 1 }])

    expect(questionAt(state.document, path)?.validators).toHaveLength(1)
    expect(questionAt(state.document, path)?.choices).toHaveLength(2)
  })

  it("adds a choice whose value nothing else in the question uses", () => {
    const state = run([
      { type: "insertItem", path, list: "choices" },
      { type: "insertItem", path, list: "choices" },
    ])

    expect(questionAt(state.document, path)?.choices.map((one) => one.value)).toEqual([
      "vanilla",
      "salt",
      "option",
      "option-2",
    ])
  })
})

describe("columns", () => {
  it("declares and clears a layer's own column count", () => {
    const set = run([{ type: "setColumns", path: { page: 0 }, range: "mobile", columns: 2 }])
    expect(set.document.pages[0]?.columns).toEqual({ mobile: 2 })

    const cleared = run(
      [{ type: "setColumns", path: { page: 0 }, range: "mobile", columns: null }],
      set,
    )
    expect(cleared.document.pages[0]?.columns).toEqual({})
  })

  it("keeps the version's own columns separate from a page's", () => {
    const state = run([{ type: "setColumns", path: null, range: "desktop", columns: 12 }])

    expect(state.document.columns).toEqual({ mobile: 4, desktop: 12 })
    expect(state.document.pages[0]?.columns).toEqual({})
  })

  it("sets a question's minimum columns", () => {
    const path = { page: 0, section: 0, question: 0 }
    const state = run([{ type: "setMinimumColumns", path, range: "mobile", columns: 12 }])

    expect(questionAt(state.document, path)?.minimumColumns).toEqual({ mobile: 12 })
  })
})

// ------------------------------------------------------------------- saving

describe("what goes back to the server", () => {
  it("drops what only the server writes", () => {
    const withServerFields: QuestionnaireDefinition = {
      ...document(),
      state: {
        responseCount: 3,
        requiresAcknowledgement: true,
        isPublished: true,
        fingerprint: "abc",
      },
    }
    withServerFields.pages[0]!.sections[0]!.questions[0]!.resolved = {
      widget: "select",
      fingerprint: "def",
    }

    const outgoing = outgoingDocument(withServerFields)

    expect(outgoing.state).toBeUndefined()
    expect(outgoing.pages[0]?.sections[0]?.questions[0]).not.toHaveProperty("resolved")
    expect(outgoing.pages[0]?.sections[0]?.questions[0]?.key).toBe("flavour")
  })

  it("knows whether anything is unsaved", () => {
    const state = initialState(document())
    expect(isDirty(state)).toBe(false)

    const edited = editorReducer(state, {
      type: "patch",
      path: { page: 0 },
      patch: { title: "About you" },
    })
    expect(isDirty(edited)).toBe(true)

    expect(isDirty(editorReducer(edited, { type: "saved", document: edited.document }))).toBe(
      false,
    )
  })

  it("names the question keys whose answers a save would orphan", () => {
    const renamed = run([
      {
        type: "patch",
        path: { page: 0, section: 0, question: 0 },
        patch: { key: "favourite-flavour" },
      },
    ])

    expect(orphanedQuestionKeys(renamed)).toEqual(["flavour"])
    expect(orphanedQuestionKeys(initialState(document()))).toEqual([])
  })
})

// --------------------------------------------------------------- validation

describe("what the editor can tell before asking the server", () => {
  it("accepts a document that holds up", () => {
    expect(validateDefinition(document(), catalog)).toEqual([])
  })

  it("catches a key that would not survive a slug field", () => {
    const state = run([{ type: "patch", path: { page: 0 }, patch: { key: "About Us!" } }])

    const issues = validateDefinition(state.document, catalog)
    expect(issuesAt(issues, "pages.0").key?.[0]).toContain("letters, digits")
  })

  it("accepts the underscored keys a slug field allows", () => {
    const state = run([{ type: "patch", path: { page: 0 }, patch: { key: "about_you" } }])

    expect(validateDefinition(state.document, catalog)).toEqual([])
  })

  it("catches an empty key, because answers are stored against it", () => {
    const state = run([
      { type: "patch", path: { page: 0, section: 0, question: 0 }, patch: { key: "" } },
    ])

    expect(
      issuesAt(validateDefinition(state.document, catalog), "pages.0.sections.0.questions.0"),
    ).toHaveProperty("key")
  })

  it("catches two questions claiming the same key, wherever they sit", () => {
    const state = run([
      { type: "insert", path: { page: 0, section: 0 } },
      {
        type: "patch",
        path: { page: 0, section: 0, question: 1 },
        patch: { key: "flavour" },
      },
    ])

    const issues = validateDefinition(state.document, catalog)
    expect(issuesAt(issues, "pages.0.sections.0.questions.0").key).toBeDefined()
    expect(issuesAt(issues, "pages.0.sections.0.questions.1").key).toBeDefined()
  })

  it("catches configuration the question type does not take", () => {
    const state = run([
      {
        type: "patch",
        path: { page: 0, section: 0, question: 0 },
        patch: { questionType: "free_text" },
      },
    ])

    const errors = issuesAt(
      validateDefinition(state.document, catalog),
      "pages.0.sections.0.questions.0",
    )
    expect(errors.choices).toBeDefined()
  })

  it("catches a list of items with no item type", () => {
    const state = run([
      {
        type: "patch",
        path: { page: 0, section: 0, question: 0 },
        patch: { questionType: "item_list", choices: [], validators: [] },
      },
    ])

    expect(
      issuesAt(validateDefinition(state.document, catalog), "pages.0.sections.0.questions.0")
        .itemQuestionType,
    ).toBeDefined()
  })

  it("catches a validator that does not apply to the question's type", () => {
    const state = run([
      {
        type: "patchItem",
        path: { page: 0, section: 0, question: 0 },
        list: "validators",
        index: 0,
        patch: { validator: "min_length" },
      },
    ])

    const issues = validateDefinition(state.document, catalog)
    expect(
      issuesAt(issues, "pages.0.sections.0.questions.0.validators.0").validator?.[0],
    ).toContain("does not apply")
  })

  it("catches two choices storing the same value", () => {
    const state = run([
      {
        type: "patchItem",
        path: { page: 0, section: 0, question: 0 },
        list: "choices",
        index: 1,
        patch: { value: "vanilla" },
      },
    ])

    const issues = validateDefinition(state.document, catalog)
    expect(issuesAt(issues, "pages.0.sections.0.questions.0.choices.1").value).toBeDefined()
  })

  it("checks nothing type-specific without a catalog to check against", () => {
    expect(validateDefinition(document(), null)).toEqual([])
  })

  it("reads back as one line per problem", () => {
    const state = run([{ type: "patch", path: { page: 0 }, patch: { title: "" } }])

    expect(summariseIssues(validateDefinition(state.document, catalog))).toEqual([
      "pages.0 title: A page needs a title.",
    ])
  })
})

describe("keys", () => {
  it("slugifies a title", () => {
    expect(slugify("What is your Company's name?")).toBe("what-is-your-company-s-name")
    expect(slugify("  ")).toBe("")
  })

  it("counts up until the key is free", () => {
    expect(uniqueKey("page", [])).toBe("page")
    expect(uniqueKey("page", ["page"])).toBe("page-2")
    expect(uniqueKey("page", ["page", "page-2"])).toBe("page-3")
  })
})
