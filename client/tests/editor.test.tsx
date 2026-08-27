// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
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
  ],
  scalarQuestionTypes: ["free_text"],
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

async function open(api: EditorApi) {
  render(<QuestionnaireEditor api={api} questionnaire="intake" version={1} />)
  await screen.findByText("About")
  return api
}

describe("the editor", () => {
  it("renders the outline from the document it fetched", async () => {
    await open(fakeApi())

    expect(screen.getByText("About")).toBeTruthy()
    expect(screen.getByText("Basics")).toBeTruthy()
    expect(screen.getByText("Your name")).toBeTruthy()
    // A page that can be skipped says so without being opened.
    expect(screen.getByText("skippable")).toBeTruthy()
  })

  it("opens the version itself first", async () => {
    await open(fakeApi())

    expect((screen.getByLabelText("Title") as HTMLInputElement).value).toBe("Intake form")
  })

  it("shows a question's own form when it is picked", async () => {
    await open(fakeApi())

    fireEvent.click(screen.getByText("Your name"))

    expect((screen.getByLabelText("Key") as HTMLInputElement).value).toBe("name")
    expect(screen.getByLabelText("Question type")).toBeTruthy()
    // The validator's params are rendered from its own schema, not hard-coded.
    expect((screen.getByLabelText("Minimum *") as HTMLInputElement).value).toBe("2")
  })

  it("does not offer choices to a type that does not take them", async () => {
    await open(fakeApi())
    fireEvent.click(screen.getByText("Your name"))

    expect(screen.queryByText("Choices")).toBeNull()
  })

  it("sends what was edited, without the fields only the server writes", async () => {
    const api = await open(fakeApi())

    fireEvent.click(screen.getByText("About"))
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

    fireEvent.click(screen.getByText("About"))
    fireEvent.change(screen.getByLabelText("Key"), { target: { value: "About Us" } })
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

    fireEvent.click(screen.getByText("About"))
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

    expect(screen.getByText("Untitled page")).toBeTruthy()
    expect(screen.getByText("Untitled section")).toBeTruthy()
  })

  it("warns about the answers a renamed key would orphan", async () => {
    await open(fakeApi())

    fireEvent.click(screen.getByText("Your name"))
    fireEvent.change(screen.getByLabelText("Key"), { target: { value: "full-name" } })

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

    fireEvent.click(screen.getByText("About"))
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

    fireEvent.click(screen.getByText("About"))
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
