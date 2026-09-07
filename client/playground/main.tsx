/**
 * The playground: both halves of the package, driven without a server.
 *
 * `npm run playground` from `client/`.
 *
 * Two things are worth having on screen at once here. The editor is what an
 * author uses, and the form is what a respondent gets -- and they are the same
 * widgets through the same registry, which is far easier to believe when the
 * two are a click apart. The form tab also takes a width, so what the editor's
 * preview claims can be checked against the thing itself.
 *
 * This is not shipped: `package.json` publishes `dist` only.
 */

import { StrictMode, useCallback, useMemo, useState } from "react"
import { createRoot } from "react-dom/client"

import { QuestionnaireEditor } from "../src/editor/index.js"
import { planFromDefinition } from "../src/preview.js"
import { QuestionnaireView, registerWidget, unregisterWidget } from "../src/widgets/index.js"
import type { WidgetProps } from "../src/widgets/index.js"
import type { QuestionnaireDefinition } from "../src/definition.js"
import "../src/editor.css"
import "../src/widgets.css"
import "./playground.css"

import { catalog, document as fixture, fakeApi } from "./fixture.js"

type Tab = "editor" | "form"
type Theme = "light" | "dark"

/**
 * A replacement for one shipped widget, to prove overriding works.
 *
 * Registered and unregistered by a switch rather than at module scope, because
 * what is worth seeing is the swap: the same question, rendered by the
 * package's radio group and then by something else, with nothing else changing.
 */
function LoudRadioGroup({ question, value, onChange, id }: WidgetProps) {
  return (
    <div className="pg-loud" role="radiogroup" aria-labelledby={`${id}-label`}>
      {(question.choices ?? []).map((choice) => (
        <button
          type="button"
          key={choice.value}
          className={`pg-loud__option${value === choice.value ? " is-chosen" : ""}`}
          aria-pressed={value === choice.value}
          onClick={() => onChange(choice.value)}
        >
          {choice.label || choice.value}
        </button>
      ))}
    </div>
  )
}

function Playground() {
  const [tab, setTab] = useState<Tab>("editor")
  const [theme, setTheme] = useState<Theme>("light")
  const [width, setWidth] = useState(1280)
  const [overridden, setOverridden] = useState(false)
  const [document, setDocument] = useState<QuestionnaireDefinition>(fixture)
  const [answers, setAnswers] = useState<Record<string, unknown>>({})

  // Re-created only when the fixture module reloads, so the editor is not
  // re-fetched on every keystroke of the playground's own controls.
  const api = useMemo(() => fakeApi(setDocument), [])
  const plan = useMemo(() => planFromDefinition(document, catalog), [document])

  const toggleOverride = useCallback((on: boolean) => {
    setOverridden(on)
    if (on) registerWidget("radio-group", LoudRadioGroup)
    else unregisterWidget("radio-group")
  }, [])

  return (
    <div className="pg" data-theme={theme}>
      <header className="pg__bar">
        <div className="pg__tabs" role="tablist" aria-label="What to show">
          {(["editor", "form"] as Tab[]).map((entry) => (
            <button
              type="button"
              key={entry}
              role="tab"
              aria-selected={tab === entry}
              className={`pg__tab${tab === entry ? " is-selected" : ""}`}
              onClick={() => setTab(entry)}
            >
              {entry === "editor" ? "Editor" : "The form itself"}
            </button>
          ))}
        </div>

        <div className="pg__controls">
          {tab === "form" ? (
            <label className="pg__control">
              Width
              <input
                type="range"
                min={320}
                max={1600}
                step={20}
                value={width}
                onChange={(event) => setWidth(Number(event.target.value))}
              />
              <output className="pg__readout">{width}px</output>
            </label>
          ) : null}

          <label className="pg__control">
            <input
              type="checkbox"
              checked={overridden}
              onChange={(event) => toggleOverride(event.target.checked)}
            />
            Override <code>radio-group</code>
          </label>

          <label className="pg__control">
            <input
              type="checkbox"
              checked={theme === "dark"}
              onChange={(event) => setTheme(event.target.checked ? "dark" : "light")}
            />
            Dark
          </label>
        </div>
      </header>

      {tab === "editor" ? (
        <QuestionnaireEditor
          // Keyed on the override, because a widget swap has to reach the
          // preview and React has no reason to re-render for a change made to
          // a module-level registry.
          key={`editor-${overridden}`}
          api={api}
          questionnaire="intake"
          version={2}
          theme={theme}
          onSaved={setDocument}
        />
      ) : (
        <div className="pg__stage">
          <div className="pg__sheet" style={{ width: `${width}px` }}>
            <QuestionnaireView
              key={`form-${overridden}`}
              plan={plan}
              answers={answers}
              width={width}
              onChange={(key, value) => setAnswers((current) => ({ ...current, [key]: value }))}
              // Whatever is typed shows up here, so the answer shapes each
              // widget reports are visible rather than taken on trust.
              errors={{}}
            />
          </div>
          <pre className="pg__answers" aria-label="The answers so far">
            {JSON.stringify(answers, null, 2)}
          </pre>
        </div>
      )}
    </div>
  )
}

createRoot(globalThis.document.getElementById("root")!).render(
  <StrictMode>
    <Playground />
  </StrictMode>,
)
