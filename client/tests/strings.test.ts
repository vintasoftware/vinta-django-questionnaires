import { describe, expect, it } from "vitest"

import { defaultStrings, resolveStrings, translate, translator } from "../src/strings.js"

describe("the string catalogue", () => {
  it("says the English default when nothing overrides it", () => {
    expect(translate(resolveStrings(), "editor.save")).toBe("Save")
  })

  it("is handed its parameters by name", () => {
    expect(translate(defaultStrings, "sortable.reorder", { name: "page About" })).toBe(
      "Reorder page About",
    )
  })

  it("takes a host's wording over its own", () => {
    const t = translator(resolveStrings({ "editor.save": "Salvar" }))

    expect(t("editor.save")).toBe("Salvar")
    // Untouched keys are still there, in English.
    expect(t("editor.revert")).toBe("Revert")
  })

  it("lets a translation put a parameter wherever its sentence wants it", () => {
    const t = translator(
      resolveStrings({ "sortable.reorder": ({ name }) => `${name} reordenar` }),
    )

    expect(t("sortable.reorder", { name: "página" })).toBe("página reordenar")
  })

  it("lets a translation count, which a template could not", () => {
    const t = translator(
      resolveStrings({
        "version.responses": ({ count }) =>
          count === 1
            ? "1 resposta já foi dada a esta versão."
            : `${count} respostas já foram dadas a esta versão.`,
      }),
    )

    expect(t("version.responses", { count: 1 })).toBe("1 resposta já foi dada a esta versão.")
    expect(t("version.responses", { count: 4 })).toBe(
      "4 respostas já foram dadas a esta versão.",
    )
  })

  it("hands the same parameters to a host's own i18n library", () => {
    // What a react-i18next or FormatJS host writes: the catalogue is the
    // wiring, and the library it already has does the sentence.
    const seen: Array<[string, Record<string, unknown>]> = []
    const theirs = (key: string, params: Record<string, unknown>) => {
      seen.push([key, params])
      return "whatever they returned"
    }
    const t = translator(
      resolveStrings({
        "editor.issues.heading": ({ count }) => theirs("editor.issues.heading", { count }),
      }),
    )

    expect(t("editor.issues.heading", { count: 3 })).toBe("whatever they returned")
    expect(seen).toEqual([["editor.issues.heading", { count: 3 }]])
  })

  it("takes a plain string for the messages that stand on their own", () => {
    // Which is most of them, and which is what a catalogue arriving as data
    // already looks like -- no wrapping needed to hand one over.
    const fromJson: Record<string, string> = { "editor.save": "Salvar" }
    const t = translator(resolveStrings(fromJson))

    expect(t("editor.save")).toBe("Salvar")
  })
})
