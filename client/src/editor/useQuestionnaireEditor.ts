/**
 * The editor, without the interface.
 *
 * Everything `<QuestionnaireEditor>` does is here: fetching the catalog and the
 * document, holding the reducer, checking what can be checked locally, saving,
 * and forking. A project that wants its own interface can take this hook and
 * render whatever it likes from it.
 */

import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react"

import type { DefinitionIssue, EditorCatalog, QuestionnaireDefinition } from "../definition.js"
import {
  DefinitionRejected,
  type EditAcknowledgement,
  type EditorApi,
} from "../editorClient.js"
import {
  editorReducer,
  initialState,
  isDirty,
  orphanedQuestionKeys,
  outgoingDocument,
  validateDefinition,
  type EditorAction,
  type EditorState,
  type Selection,
} from "../editorState.js"

const EMPTY: QuestionnaireDefinition = {
  documentVersion: 1,
  questionnaire: { key: "", name: "" },
  version: 0,
  title: "",
  description: "",
  status: "draft",
  editPolicy: "",
  responsesDueAt: null,
  editsDueAt: null,
  windowSizeRanges: [],
  columns: {},
  pages: [],
}

export interface UseQuestionnaireEditorOptions {
  api: EditorApi
  questionnaire: string
  version: number
  /** Called after every accepted save, with what the server sent back. */
  onSaved?: (document: QuestionnaireDefinition) => void
  /** Called after a fork, with the new draft. */
  onForked?: (document: QuestionnaireDefinition) => void
}

export interface QuestionnaireEditor {
  state: EditorState
  dispatch: (action: EditorAction) => void
  catalog: EditorCatalog | null
  /** True until both the catalog and the document have arrived. */
  isLoading: boolean
  isSaving: boolean
  /** Whatever went wrong that was not a rejected document. */
  error: Error | null
  /** What the server refused, plus what the editor can tell on its own. */
  issues: DefinitionIssue[]
  /** Only the ones the editor found itself, before any save. */
  localIssues: DefinitionIssue[]
  isDirty: boolean
  /** Whether this version has responses, so edits have to be acknowledged. */
  requiresAcknowledgement: boolean
  /** Questions whose key has gone since the last save: orphaned answers. */
  orphanedKeys: string[]
  select: (selection: Selection) => void
  save: (acknowledgement?: EditAcknowledgement) => Promise<boolean>
  reload: () => Promise<void>
  fork: (title?: string) => Promise<QuestionnaireDefinition | null>
  revert: () => void
}

export function useQuestionnaireEditor(
  options: UseQuestionnaireEditorOptions,
): QuestionnaireEditor {
  const { api, questionnaire, version } = options
  const [state, dispatch] = useReducer(editorReducer, EMPTY, initialState)
  const [catalog, setCatalog] = useState<EditorCatalog | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  // Held in refs so `save` does not have to be rebuilt whenever the document
  // changes or the caller passes a fresh inline callback -- either would
  // restart every effect that depends on it.
  const latest = useRef(state)
  latest.current = state
  const handlers = useRef(options)
  handlers.current = options

  useEffect(() => {
    const controller = new AbortController()
    setIsLoading(true)
    setError(null)
    Promise.all([
      api.fetchCatalog(controller.signal),
      api.fetchDefinition(questionnaire, version, controller.signal),
    ])
      .then(([fetchedCatalog, document]) => {
        if (controller.signal.aborted) return
        setCatalog(fetchedCatalog)
        dispatch({ type: "loaded", document })
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return
        setError(asError(cause))
      })
      .finally(() => {
        if (!controller.signal.aborted) setIsLoading(false)
      })
    return () => controller.abort()
  }, [api, questionnaire, version])

  const localIssues = useMemo(
    () => validateDefinition(state.document, catalog),
    [state.document, catalog],
  )
  // What the server refused stays visible until the next save clears it, so
  // both halves of the picture are on screen at once.
  const issues = useMemo(
    () => mergeIssues(state.issues, localIssues),
    [state.issues, localIssues],
  )

  const save = useCallback(
    async (acknowledgement?: EditAcknowledgement) => {
      const current = latest.current
      const local = validateDefinition(current.document, catalog)
      if (local.length) {
        dispatch({ type: "issues", issues: local })
        return false
      }
      setIsSaving(true)
      setError(null)
      try {
        const saved = await api.saveDefinition(
          questionnaire,
          version,
          outgoingDocument(current.document),
          acknowledgement,
        )
        dispatch({ type: "saved", document: saved })
        handlers.current.onSaved?.(saved)
        return true
      } catch (cause: unknown) {
        if (cause instanceof DefinitionRejected) {
          dispatch({ type: "issues", issues: cause.issues })
        } else {
          setError(asError(cause))
        }
        return false
      } finally {
        setIsSaving(false)
      }
    },
    [api, catalog, questionnaire, version],
  )

  const reload = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      dispatch({
        type: "loaded",
        document: await api.fetchDefinition(questionnaire, version),
      })
    } catch (cause: unknown) {
      setError(asError(cause))
    } finally {
      setIsLoading(false)
    }
  }, [api, questionnaire, version])

  const fork = useCallback(
    async (title?: string) => {
      setIsSaving(true)
      setError(null)
      try {
        const draft = await api.forkVersion(questionnaire, version, title)
        handlers.current.onForked?.(draft)
        return draft
      } catch (cause: unknown) {
        setError(asError(cause))
        return null
      } finally {
        setIsSaving(false)
      }
    },
    [api, questionnaire, version],
  )

  const select = useCallback(
    (selection: Selection) => dispatch({ type: "select", selection }),
    [],
  )
  const revert = useCallback(
    () => dispatch({ type: "loaded", document: latest.current.saved }),
    [],
  )

  return {
    state,
    dispatch,
    catalog,
    isLoading,
    isSaving,
    error,
    issues,
    localIssues,
    isDirty: isDirty(state),
    requiresAcknowledgement: !!state.saved.state?.requiresAcknowledgement,
    orphanedKeys: orphanedQuestionKeys(state),
    select,
    save,
    reload,
    fork,
    revert,
  }
}

function asError(cause: unknown): Error {
  return cause instanceof Error ? cause : new Error(String(cause))
}

function mergeIssues(
  fromServer: readonly DefinitionIssue[],
  fromHere: readonly DefinitionIssue[],
): DefinitionIssue[] {
  const seen = new Set<string>()
  const merged: DefinitionIssue[] = []
  for (const issue of [...fromServer, ...fromHere]) {
    const identity = JSON.stringify(issue)
    if (seen.has(identity)) continue
    seen.add(identity)
    merged.push(issue)
  }
  return merged
}
