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
 */

import { useState } from "react"

import { pathOf, questionAt, sectionAt, pageAt, summariseIssues } from "../editorState.js"
import type { EditorApi } from "../editorClient.js"
import type { QuestionnaireDefinition } from "../definition.js"
import { Outline } from "./Outline.js"
import { PageForm, QuestionForm, SectionForm, VersionForm } from "./forms.js"
import { Button, Checkbox, TextInput } from "./fields.js"
import { useQuestionnaireEditor } from "./useQuestionnaireEditor.js"

export interface QuestionnaireEditorProps {
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
  const editor = useQuestionnaireEditor(props)
  const { state, dispatch, issues } = editor
  const [reason, setReason] = useState("")
  const [understood, setUnderstood] = useState(false)

  if (editor.isLoading) {
    return (
      <div className="vqe vqe--loading" data-vqe-theme={props.theme}>
        Loading the questionnaire...
      </div>
    )
  }
  if (editor.error && !state.document.questionnaire.key) {
    return (
      <div className="vqe vqe--error" role="alert" data-vqe-theme={props.theme}>
        {editor.error.message}
        <Button onClick={() => void editor.reload()}>Try again</Button>
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
          {editor.isDirty ? <span className="vqe-badge vqe-badge--warn">unsaved</span> : null}
        </div>
        <div className="vqe__bar-actions">
          <Button onClick={() => editor.revert()} disabled={!editor.isDirty}>
            Revert
          </Button>
          <Button onClick={() => void editor.fork()} disabled={editor.isSaving}>
            Fork into a new draft
          </Button>
          <Button
            variant="primary"
            disabled={!canSave}
            onClick={() => void editor.save(gated ? { understood, reason } : undefined)}
          >
            {editor.isSaving ? "Saving..." : "Save"}
          </Button>
        </div>
      </header>

      {gated ? (
        <section className="vqe__notice" role="note">
          <p>
            This version already has{" "}
            <strong>{state.saved.state?.responseCount ?? 0} response(s)</strong>. Changing what
            a question asks changes what those answers mean. The ordinary way to make a change
            like this is to fork a new draft; editing in place is allowed, and recorded.
          </p>
          <Checkbox
            label="I understand what this edit does to the responses already given."
            checked={understood}
            onChange={setUnderstood}
          />
          <TextInput
            label="Reason"
            hint="Kept with the record of the edit."
            value={reason}
            onChange={setReason}
          />
        </section>
      ) : null}

      {editor.orphanedKeys.length ? (
        <section className="vqe__notice vqe__notice--warn" role="note">
          These question keys are gone since the last save, so the answers stored against them
          will no longer be read: <code>{editor.orphanedKeys.join(", ")}</code>
        </section>
      ) : null}

      {editor.error ? (
        <section className="vqe__notice vqe__notice--error" role="alert">
          {editor.error.message}
        </section>
      ) : null}

      {issues.length ? (
        <section className="vqe__notice vqe__notice--error" role="alert">
          <p>{issues.length} thing(s) need fixing before this can be saved:</p>
          <ul>
            {summariseIssues(issues)
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
  return <p className="vqe-form__hint">That is gone. Pick something from the outline.</p>
}
