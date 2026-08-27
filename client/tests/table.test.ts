import { describe, expect, it } from "vitest"

import {
  cellText,
  groupColumns,
  responseQueryString,
  type ResponseColumn,
} from "../src/table.js"

const column = (over: Partial<ResponseColumn>): ResponseColumn => ({
  key: "k",
  label: "K",
  group: "answer",
  page: "",
  section: "",
  questionType: "",
  ...over,
})

describe("the response table", () => {
  it("renders a cell the way the CSV export does", () => {
    expect(cellText(null)).toBe("")
    expect(cellText(undefined)).toBe("")
    expect(cellText("hugo")).toBe("hugo")
    expect(cellText(40)).toBe("40")
    expect(cellText(true)).toBe("true")
    expect(cellText(["python", "typescript"])).toBe("python, typescript")
    expect(cellText({ monday: ["morning"] })).toBe('{"monday":["morning"]}')
  })

  it("builds the query string both endpoints read", () => {
    const query = responseQueryString({
      questionnaire: "intake",
      version: 2,
      page: 3,
      pageSize: 50,
      columns: ["id", "email"],
    })

    expect(new URLSearchParams(query).get("questionnaire")).toBe("intake")
    expect(new URLSearchParams(query).get("columns")).toBe("id,email")
    expect(new URLSearchParams(query).get("status")).toBeNull()
  })

  it("groups the columns for a picker: the response first, then by page", () => {
    const groups = groupColumns([
      column({ key: "id", group: "meta" }),
      column({ key: "email", page: "About" }),
      column({ key: "budget", page: "Project" }),
      column({ key: "name", page: "About" }),
    ])

    expect(groups.map((group) => group.title)).toEqual(["The response", "About", "Project"])
    expect(groups[1]?.columns.map((entry) => entry.key)).toEqual(["email", "name"])
  })
})
