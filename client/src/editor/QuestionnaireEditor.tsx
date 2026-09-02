/**
 * The drop-in editor.
 *
 * ```tsx
 * import { QuestionnaireEditor } from "vinta-django-questionnaires-client/editor"
 * import "vinta-django-questionnaires-client/editor.css"
 *
 * <QuestionnaireEditor
 *   api={createEditorClient({ baseUrl: "/api/authoring/" })}
 *   questionnaire="intake"
 *   version={2}
 * />
 * ```
 *
 * It is one component over `useQuestionnaireEditor`, and everything it renders
 * carries a `vqe-` class name -- so a project can restyle it entirely from its
 * own stylesheet, or skip it and build its own interface on the hook.
 *
 * Every word it says comes from `strings`, so a project translates it by
 * passing a catalogue rather than by forking the component.
 */

import { useState } from "react"

import { pathOf, questionAt, sectionAt, pageAt, summariseIssues } from "../editorState.js"
import type { EditorApi } from "../editorClient.js"
import type { QuestionnaireDefinition } from "../definition.js"
import { Outline } from "./Outline.js"
import { PageForm, QuestionForm, SectionForm, VersionForm } from "./forms.js"
import { Button, Checkbox, TextInput } from "./fields.js"
import {
  QuestionnaireStringsProvider,
  useStringCatalog,
  useStrings,
  type WithStrings,
} from "./strings.js"
import { useQuestionnaireEditor } from "./useQuestionnaireEditor.js"

export interface QuestionnaireEditorProps extends WithStrings {
  api: EditorApi
  questionnaire: string
  version: number
  onSaved?: (document: QuestionnaireDefinition) => void
  /** Called with the new draft after a fork. Point the editor at it. */
  onForked?: (document: QuestionnaireDefinition) => void
  className?: string
  /** The editor's palette. Light unless the host says otherwise. */
  theme?: "light" | "dark"
}

export function QuestionnaireEditor(props: QuestionnaireEditorProps) {
  // The provider wraps the whole subtree, so the outline and the forms are
  // translated by the same catalogue without being handed it one by one.
  return (
    <QuestionnaireStringsProvider strings={props.strings}>
      <Editor {...props} />
    </QuestionnaireStringsProvider>
  )
}

function Editor(props: QuestionnaireEditorProps) {
  const editor = useQuestionnaireEditor(props)
  const { state, dispatch, issues } = editor
  const t = useStrings()
  const strings = useStringCatalog()
  const [reason, setReason] = useState("")
  const [understood, setUnderstood] = useState(false)

  if (editor.isLoading) {
    return (
      <div className="vqe vqe--loading" data-vqe-theme={props.theme}>
        {t("editor.loading")}
      </div>
    )
  }
  if (editor.error && !state.document.questionnaire.key) {
    return (
      <div className="vqe vqe--error" role="alert" data-vqe-theme={props.theme}>
        {editor.error.message}
        <Button onClick={() => void editor.reload()}>{t("editor.retry")}</Button>
      </div>
    )
  }

  const gated = editor.requiresAcknowledgement
  const canSave = editor.isDirty && !editor.isSaving && (!gated || understood)

  return (
    <div className={`vqe ${props.className ?? ""}`.trim()} data-vqe-theme={props.theme}>
      <header className="vqe__bar">
        <div className="vqe__bar-title">
          <strong>{state.document.title || state.document.questionnaire.name}</strong>
          <span className="vqe-badge">v{state.document.version}</span>
          <span className="vqe-badge">{state.document.status}</span>
          {editor.isDirty ? (
            <span className="vqe-badge vqe-badge--warn">{t("editor.badge.unsaved")}</span>
          ) : null}
        </div>
        <div className="vqe__bar-actions">
          <Button onClick={() => editor.revert()} disabled={!editor.isDirty}>
            {t("editor.revert")}
          </Button>
          <Button onClick={() => void editor.fork()} disabled={editor.isSaving}>
            {t("editor.fork")}
          </Button>
          <Button
            variant="primary"
            disabled={!canSave}
            onClick={() => void editor.save(gated ? { understood, reason } : undefined)}
          >
            {t(editor.isSaving ? "editor.saving" : "editor.save")}
          </Button>
        </div>
      </header>

      {gated ? (
        <section className="vqe__notice" role="note">
          <p>
            {t("editor.acknowledge.notice", {
              count: state.saved.state?.responseCount ?? 0,
            })}
          </p>
          <Checkbox
            label={t("editor.acknowledge.understood")}
            checked={understood}
            onChange={setUnderstood}
          />
          <TextInput
            label={t("editor.acknowledge.reason")}
            hint={t("editor.acknowledge.reasonHint")}
            value={reason}
            onChange={setReason}
          />
        </section>
      ) : null}

      {editor.orphanedKeys.length ? (
        <section className="vqe__notice vqe__notice--warn" role="note">
          {t("editor.orphaned", { keys: editor.orphanedKeys.join(", ") })}
        </section>
      ) : null}

      {editor.error ? (
        <section className="vqe__notice vqe__notice--error" role="alert">
          {editor.error.message}
        </section>
      ) : null}

      {issues.length ? (
        <section className="vqe__notice vqe__notice--error" role="alert">
          <p>{t("editor.issues.heading", { count: issues.length })}</p>
          <ul>
            {summariseIssues(issues, strings)
              .slice(0, 10)
              .map((message, index) => (
                <li key={index}>{message}</li>
              ))}
          </ul>
        </section>
      ) : null}

      <div className="vqe__body">
        <Outline
          document={state.document}
          selection={state.selection}
          issues={issues}
          dispatch={dispatch}
        />
        <main className="vqe__inspector">
          <Inspector editor={editor} />
        </main>
      </div>
    </div>
  )
}

function Inspector({ editor }: { editor: ReturnType<typeof useQuestionnaireEditor> }) {
  const { state, catalog, issues, dispatch } = editor
  const { selection, document } = state
  const shared = { catalog, issues, dispatch }

  if (selection.kind === "page") {
    const page = pageAt(document, selection)
    if (!page) return <Missing />
    return <PageForm {...shared} page={page} path={selection} document={document} />
  }
  if (selection.kind === "section") {
    const section = sectionAt(document, selection)
    if (!section) return <Missing />
    return <SectionForm {...shared} section={section} path={selection} document={document} />
  }
  if (selection.kind === "question") {
    const question = questionAt(document, selection)
    if (!question) return <Missing />
    return (
      <QuestionForm
        {...shared}
        key={pathOf(selection)}
        question={question}
        path={selection}
        document={document}
      />
    )
  }
  return <VersionForm {...shared} document={document} />
}

function Missing() {
  const t = useStrings()
  return <p className="vqe-form__hint">{t("editor.missing")}</p>
}
