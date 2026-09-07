// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import type { EditorCatalog, QuestionnaireDefinition } from "../src/definition.js"
import { DefinitionRejected, type EditorApi } from "../src/editorClient.js"
import { QuestionnaireEditor } from "../src/editor/index.js"

afterEach(cleanup)

function document(overrides: Partial<QuestionnaireDefinition> = {}): QuestionnaireDefinition {
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
    windowSizeRanges: [{ key: "mobile", label: "Mobile", minWidth: 0, maxWidth: 767 }],
    columns: {},
    state: {
      responseCount: 0,
      requiresAcknowledgement: false,
      isPublished: false,
      fingerprint: "abc",
    },
    pages: [
      {
        key: "about",
        title: "About",
        description: "",
        conclusion: "",
        condition: "",
        isSkippable: true,
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
                key: "name",
                title: "Your name",
                description: "",
                questionType: "free_text",
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
                validators: [
                  {
                    validator: "min_length",
                    params: { minimum: 2 },
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
    ...overrides,
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
      key: "single_option",
      label: "Single option",
      answerShape: "scalar",
      supportsChoices: true,
      supportsValueSet: true,
      supportsOtherOption: true,
      usesMatrixAxes: false,
      requiresItemType: false,
      requiresSubQuestionnaire: false,
    },
  ],
  scalarQuestionTypes: ["free_text", "single_option"],
  validators: [
    {
      key: "min_length",
      label: "Minimum length",
      description: "Not shorter than the minimum.",
      paramsSchema: {
        type: "object",
        properties: { minimum: { type: "integer", title: "Minimum" } },
        required: ["minimum"],
      },
      errorKeys: [{ key: "too_short", message: "Too short." }],
      questionTypes: null,
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

function fakeApi(overrides: Partial<EditorApi> = {}, initial = document()): EditorApi {
  return {
    fetchCatalog: vi.fn(async () => catalog),
    fetchDefinition: vi.fn(async () => initial),
    saveDefinition: vi.fn(async (_q, _v, sent) => sent),
    forkVersion: vi.fn(async () => initial),
    ...overrides,
  }
}

/** The same document, with a question that carries choices of its own. */
function withChoices(): QuestionnaireDefinition {
  const base = document()
  const question = base.pages[0]!.sections[0]!.questions[0]!
  base.pages[0]!.sections[0]!.questions.push({
    ...question,
    key: "flavour",
    title: "Pick one",
    questionType: "single_option",
    validators: [],
    choices: [
      { axis: "option", value: "y", label: "Yes", isActive: true, extra: {} },
      { axis: "option", value: "n", label: "No", isActive: true, extra: {} },
    ],
  })
  return base
}

/**
 * The outline rail, to query inside.
 *
 * The preview renders the same page and question titles the outline does, so a
 * bare `outline().getByText("About")` now matches twice. Scoping says which of the
 * two a test meant, which was always the outline for these.
 */
function outline() {
  return within(screen.getByRole("navigation", { name: "Questionnaire outline" }))
}

/** The same, awaited: the rail only exists once the fetch has come back. */
async function findOutline() {
  return within(await screen.findByRole("navigation", { name: "Questionnaire outline" }))
}

/**
 * Reveal the key field.
 *
 * It is help text with an Edit button until someone asks for it, so a test that
 * wants to type a key has to ask the same way a person does.
 */
function editKey() {
  fireEvent.click(screen.getByRole("button", { name: "Edit" }))
  return screen.getByLabelText("Key") as HTMLInputElement
}

/**
 * Type *text* into a field one character at a time.
 *
 * `fireEvent.change` sets the whole value in one event, which is a paste rather
 * than typing -- and the difference is not academic. A rule that looks at the
 * field's current value on every keystroke behaves completely differently under
 * the two, which is exactly how a bug that stopped the key after its first
 * character got past a test that used `change`.
 */
function type(field: HTMLElement, text: string) {
  for (let length = 1; length <= text.length; length += 1) {
    fireEvent.change(field, { target: { value: text.slice(0, length) } })
  }
}

async function open(api: EditorApi) {
  render(<QuestionnaireEditor api={api} questionnaire="intake" version={1} />)
  await (await findOutline()).findByText("About")
  return api
}

describe("the editor", () => {
  it("renders the outline from the document it fetched", async () => {
    await open(fakeApi())

    expect(outline().getByText("About")).toBeTruthy()
    expect(outline().getByText("Basics")).toBeTruthy()
    expect(outline().getByText("Your name")).toBeTruthy()
    // A page that can be skipped says so without being opened.
    expect(outline().getByText("skippable")).toBeTruthy()
  })

  it("opens the version itself first", async () => {
    await open(fakeApi())

    expect((screen.getByLabelText("Title") as HTMLInputElement).value).toBe("Intake form")
  })

  it("shows a question's own form when it is picked", async () => {
    await open(fakeApi())

    fireEvent.click(outline().getByText("Your name"))

    expect(editKey().value).toBe("name")
    expect(screen.getByLabelText("Question type")).toBeTruthy()
    // The validator's params are rendered from its own schema, not hard-coded.
    expect((screen.getByLabelText("Minimum *") as HTMLInputElement).value).toBe("2")
  })

  it("keeps the focus in a choice's value field while it is typed in", async () => {
    // The row's identity has to survive an edit to the field being typed in:
    // when it did not, every keystroke remounted the row and the field lost
    // the focus, so only one character could be typed at a time.
    await open(fakeApi({}, withChoices()))

    fireEvent.click(outline().getByText("Pick one"))
    const field = screen.getAllByLabelText("Value")[0] as HTMLInputElement
    field.focus()
    fireEvent.change(field, { target: { value: "ye" } })

    const after = screen.getAllByLabelText("Value")[0] as HTMLInputElement
    expect(after.value).toBe("ye")
    expect(globalThis.document.activeElement).toBe(after)
  })

  it("keeps an outline row through a rename of the key it is drawn from", async () => {
    // The rows used to be identified by the key they show, so renaming one
    // rebuilt its row from scratch -- which drops whatever was focused inside
    // it, the same way it dropped the focus out of a choice being typed in.
    await open(fakeApi())

    fireEvent.click(outline().getByText("Your name"))
    const row = outline().getByText("Your name")
    fireEvent.change(editKey(), { target: { value: "full-name" } })

    expect(outline().getByText("Your name")).toBe(row)
    expect((screen.getByLabelText("Key") as HTMLInputElement).value).toBe("full-name")
  })

  it("shows the key as help text rather than as a field", async () => {
    await open(fakeApi())
    fireEvent.click(outline().getByText("Your name"))

    // Readable, and out of the way: the key is the most consequential value on
    // the form and the one an author has least reason to touch.
    expect(screen.getByText("name", { selector: "code" })).toBeTruthy()
    expect(screen.queryByLabelText("Key")).toBeNull()
  })

  it("writes the key from the title of a node that has not been saved", async () => {
    await open(fakeApi())
    // Adding selects what was added, so the form on screen is the new question.
    fireEvent.click(outline().getAllByText("+ Question")[0]!)
    type(screen.getByLabelText("Title"), "Your job title")

    expect(editKey().value).toBe("your-job-title")
  })

  it("keeps following the title for every character, not just the first", async () => {
    // The bug this pins: the rule used to ask whether the key still looked like
    // one the editor had generated, which stopped being true the moment the
    // first character was typed -- so the key stuck at "y".
    await open(fakeApi())
    fireEvent.click(outline().getAllByText("+ Question")[0]!)
    const title = screen.getByLabelText("Title")

    type(title, "Your")
    expect(editKey().value).toBe("your")

    type(title, "Your job")
    expect(screen.getByLabelText("Key")).toHaveProperty("value", "your-job")
  })

  it("stops following once the key has been typed into by hand", async () => {
    await open(fakeApi())
    fireEvent.click(outline().getAllByText("+ Question")[0]!)
    type(screen.getByLabelText("Title"), "Role")
    fireEvent.change(editKey(), { target: { value: "job-role" } })

    type(screen.getByLabelText("Title"), "Role at work")

    expect((screen.getByLabelText("Key") as HTMLInputElement).value).toBe("job-role")
  })

  it("leaves a saved node's key alone as its title changes", async () => {
    // Answers are filed under it, so a title change must not rewrite a key the
    // server already knows -- that would orphan every answer given under it.
    await open(fakeApi())
    fireEvent.click(outline().getByText("Your name"))
    type(screen.getByLabelText("Title"), "Full name")

    expect(editKey().value).toBe("name")
  })

  it("stops following what it was following once it is saved", async () => {
    const api = await open(fakeApi())
    fireEvent.click(outline().getAllByText("+ Question")[0]!)
    type(screen.getByLabelText("Title"), "Role")
    expect(editKey().value).toBe("role")

    fireEvent.click(screen.getByText("Save"))
    await waitFor(() => expect(api.saveDefinition).toHaveBeenCalled())

    // The marker is the editor's own note and never leaves it.
    const sent = vi.mocked(api.saveDefinition).mock.calls[0]![2]
    expect(JSON.stringify(sent)).not.toContain("isNew")
  })

  it("opens the key field itself when the server refused the key", async () => {
    const api = fakeApi({
      saveDefinition: vi.fn(async () => {
        throw new DefinitionRejected([
          { path: "pages.0", errors: { key: ["That key is taken."] } },
        ])
      }),
    })
    await open(api)

    fireEvent.click(outline().getByText("About"))
    fireEvent.change(screen.getByLabelText("Title"), { target: { value: "About you" } })
    fireEvent.click(screen.getByText("Save"))

    // Without clicking Edit: an error under help text nobody can act on is
    // worse than no error at all.
    await screen.findByText("That key is taken.")
    expect(screen.getByLabelText("Key")).toBeTruthy()
  })

  it("does not offer choices to a type that does not take them", async () => {
    await open(fakeApi())
    fireEvent.click(outline().getByText("Your name"))

    expect(screen.queryByText("Choices")).toBeNull()
  })

  it("sends what was edited, without the fields only the server writes", async () => {
    const api = await open(fakeApi())

    fireEvent.click(outline().getByText("About"))
    fireEvent.change(screen.getByLabelText("Description"), {
      target: { value: "Tell us about yourself." },
    })
    fireEvent.click(screen.getByText("Save"))

    await waitFor(() => expect(api.saveDefinition).toHaveBeenCalled())
    const sent = vi.mocked(api.saveDefinition).mock.calls[0]![2]
    expect(sent.pages[0]?.description).toBe("Tell us about yourself.")
    expect(sent.state).toBeUndefined()
  })

  it("will not save while it can see something wrong itself", async () => {
    const api = await open(fakeApi())

    fireEvent.click(outline().getByText("About"))
    fireEvent.change(editKey(), { target: { value: "About Us" } })
    fireEvent.click(screen.getByText("Save"))

    // Once under the field, once in the summary at the top.
    expect(await screen.findAllByText(/letters, digits/)).toHaveLength(2)
    expect(api.saveDefinition).not.toHaveBeenCalled()
  })

  it("puts what the server refused under the field that caused it", async () => {
    const api = fakeApi({
      saveDefinition: vi.fn(async () => {
        throw new DefinitionRejected([
          { path: "pages.0", errors: { title: ["This title is already taken."] } },
        ])
      }),
    })
    await open(api)

    fireEvent.click(outline().getByText("About"))
    fireEvent.change(screen.getByLabelText("Title"), { target: { value: "About you" } })
    fireEvent.click(screen.getByText("Save"))

    await screen.findByText("This title is already taken.")
    // ...and the outline flags the branch it is under.
    expect(screen.getAllByLabelText("Has a problem").length).toBeGreaterThan(0)
  })

  it("adds a page, a section and a question from the outline", async () => {
    await open(fakeApi())

    fireEvent.click(screen.getByText("+ Page"))
    fireEvent.click(screen.getAllByText("+ Section")[1]!)

    expect(outline().getByText("Untitled page")).toBeTruthy()
    expect(outline().getByText("Untitled section")).toBeTruthy()
  })

  it("selects what was just added", async () => {
    await open(fakeApi())

    fireEvent.click(screen.getByText("+ Page"))

    // The page's own form, ready to be named -- not the outline row alone.
    expect(screen.getByText("Page")).toBeTruthy()
    expect((screen.getByLabelText("Title") as HTMLInputElement).value).toBe("Untitled page")
  })

  it("warns about the answers a renamed key would orphan", async () => {
    await open(fakeApi())

    fireEvent.click(outline().getByText("Your name"))
    fireEvent.change(editKey(), { target: { value: "full-name" } })

    expect(screen.getByText(/no longer be read/)).toBeTruthy()
  })

  it("refuses to save a version with responses until the box is ticked", async () => {
    const withResponses = document({
      state: {
        responseCount: 4,
        requiresAcknowledgement: true,
        isPublished: true,
        fingerprint: "abc",
      },
    })
    const api = await open(fakeApi({}, withResponses))

    fireEvent.click(outline().getByText("About"))
    fireEvent.change(screen.getByLabelText("Title"), { target: { value: "About you" } })

    const save = screen.getByText("Save") as HTMLButtonElement
    expect(save.disabled).toBe(true)

    fireEvent.click(screen.getByLabelText(/I understand what this edit does/))
    fireEvent.change(screen.getByLabelText("Reason"), { target: { value: "Clearer wording" } })
    fireEvent.click(save)

    await waitFor(() => expect(api.saveDefinition).toHaveBeenCalled())
    expect(vi.mocked(api.saveDefinition).mock.calls[0]![3]).toEqual({
      understood: true,
      reason: "Clearer wording",
    })
  })

  it("reverts to what the server last agreed to", async () => {
    await open(fakeApi())

    fireEvent.click(outline().getByText("About"))
    fireEvent.change(screen.getByLabelText("Title"), { target: { value: "Changed" } })
    expect(screen.getByText("unsaved")).toBeTruthy()

    fireEvent.click(screen.getByText("Revert"))

    expect(screen.queryByText("unsaved")).toBeNull()
  })

  it("forks the version into a new draft", async () => {
    const api = await open(fakeApi())

    fireEvent.click(screen.getByText("Fork into a new draft"))

    await waitFor(() => expect(api.forkVersion).toHaveBeenCalledWith("intake", 1, undefined))
  })

  it("says so when it cannot load anything at all", async () => {
    render(
      <QuestionnaireEditor
        api={fakeApi({
          fetchDefinition: vi.fn(async () => {
            throw new Error("Not found.")
          }),
        })}
        questionnaire="intake"
        version={1}
      />,
    )

    await screen.findByText("Not found.")
  })
})

describe("its words", () => {
  const ptBR = {
    "editor.save": "Salvar",
    "field.title": "Título",
    "field.key": "Chave",
    "outline.add.page": "+ Página",
    "editor.new.page": "Página sem título",
    "outline.badge.skippable": "pulável",
    "issue.page.title": "Uma página precisa de um título.",
    // The parameters arrive named and typed, so a translation decides where
    // they go -- and, here, how to count them.
    "editor.issues.heading": ({ count }: { count: number }) =>
      count === 1
        ? "1 coisa a corrigir antes de salvar:"
        : `${count} coisas a corrigir antes de salvar:`,
  }

  it("says whatever the catalogue passed in says", async () => {
    render(
      <QuestionnaireEditor api={fakeApi()} questionnaire="intake" version={1} strings={ptBR} />,
    )
    await (await findOutline()).findByText("About")

    expect(screen.getByText("Salvar")).toBeTruthy()
    expect(screen.getByLabelText("Título")).toBeTruthy()
    expect(outline().getByText("pulável")).toBeTruthy()
    // The catalogue reaches the outline and the forms alike, through the
    // context rather than through a prop threaded down by hand.
    expect(screen.getByText("+ Página")).toBeTruthy()
  })

  it("leaves whatever the catalogue does not cover in English", async () => {
    render(
      <QuestionnaireEditor api={fakeApi()} questionnaire="intake" version={1} strings={ptBR} />,
    )
    await (await findOutline()).findByText("About")

    expect(screen.getByText("Revert")).toBeTruthy()
    expect(screen.getByLabelText("Description")).toBeTruthy()
  })

  it("names a new node with the catalogue's word for it", async () => {
    render(
      <QuestionnaireEditor api={fakeApi()} questionnaire="intake" version={1} strings={ptBR} />,
    )
    await (await findOutline()).findByText("About")

    fireEvent.click(screen.getByText("+ Página"))

    expect(outline().getByText("Página sem título")).toBeTruthy()
  })

  it("phrases what it found wrong in the catalogue's words too", async () => {
    render(
      <QuestionnaireEditor api={fakeApi()} questionnaire="intake" version={1} strings={ptBR} />,
    )
    await (await findOutline()).findByText("About")

    fireEvent.click(outline().getByText("About"))
    fireEvent.change(screen.getByLabelText("Título"), { target: { value: "" } })
    fireEvent.click(screen.getByText("Salvar"))

    // The local checks report by key, so the catalogue words them -- and the
    // count is substituted into the heading rather than concatenated onto it.
    // Twice over: under the field it belongs to, and in the summary at the top.
    expect(screen.getAllByText(/Uma página precisa de um título/)).toHaveLength(2)
    expect(screen.getByText("1 coisa a corrigir antes de salvar:")).toBeTruthy()
  })
})
