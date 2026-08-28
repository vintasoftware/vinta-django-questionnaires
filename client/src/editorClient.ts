/**
 * Talking to the authoring API.
 *
 * A thin wrapper on `fetch` rather than a data layer: no caching, no retries,
 * no state. Projects that already have an HTTP client of their own can skip it
 * and pass their own object.
 *
 * The contract is in two halves on purpose. `EditorApi` is the four calls
 * `<QuestionnaireEditor>` makes and the whole of what it depends on, so a host
 * can satisfy it in a few lines. `AuthoringApi` adds the rest of the back
 * office -- listing, creating and deleting questionnaires, and reading
 * responses -- which the editor never touches.
 */

import type { DefinitionIssue, EditorCatalog, QuestionnaireDefinition } from "./definition.js"
import { responseQueryString, type ResponsePage, type ResponseQuery } from "./table.js"

/** What `<QuestionnaireEditor>` needs to be able to do. */
export interface EditorApi {
  fetchCatalog(signal?: AbortSignal): Promise<EditorCatalog>
  fetchDefinition(
    questionnaire: string,
    version: number,
    signal?: AbortSignal,
  ): Promise<QuestionnaireDefinition>
  saveDefinition(
    questionnaire: string,
    version: number,
    document: QuestionnaireDefinition,
    acknowledgement?: EditAcknowledgement,
  ): Promise<QuestionnaireDefinition>
  forkVersion(
    questionnaire: string,
    version: number,
    title?: string,
  ): Promise<QuestionnaireDefinition>
}

/** The whole authoring API: what the editor needs, and the rest of it. */
export interface AuthoringApi extends EditorApi {
  /** Everything there is to edit, with how many responses each version has. */
  listQuestionnaires(signal?: AbortSignal): Promise<AuthoredQuestionnaire[]>
  /** A new questionnaire and its first draft, which come together. */
  createQuestionnaire(input: NewQuestionnaire): Promise<QuestionnaireDefinition>
  deleteQuestionnaire(questionnaire: string): Promise<void>
  deleteVersion(questionnaire: string, version: number): Promise<void>
  listResponses(query: ResponseQuery, signal?: AbortSignal): Promise<ResponsePage>
  /** Where to point a download at. Not fetched: the browser does that. */
  responseExportUrl(query: ResponseQuery): string
}

export interface AuthoredVersion {
  version: number
  title: string
  status: string
  responseCount: number
}

export interface AuthoredQuestionnaire {
  /** Unique within a scope, not across the installation. */
  key: string
  name: string
  /**
   * The scope this questionnaire lives in, empty for one the whole
   * installation shares. Sent by the server so a client never has to work out
   * which of two same-keyed questionnaires it is looking at.
   */
  scope?: string
  isGlobal?: boolean
  isActive: boolean
  versions: AuthoredVersion[]
}

export interface NewQuestionnaire {
  key: string
  name?: string
  title?: string
  description?: string
}

/** Someone saying they know what editing a live version does to its responses. */
export interface EditAcknowledgement {
  understood: boolean
  reason: string
}

/** A save the server refused, with one entry per node it would not take. */
export class DefinitionRejected extends Error {
  readonly issues: DefinitionIssue[]

  constructor(issues: DefinitionIssue[]) {
    super("The server did not accept this questionnaire definition.")
    this.name = "DefinitionRejected"
    this.issues = issues
  }
}

/** Any other unhappy reply, kept whole so the caller can look at it. */
export class EditorRequestFailed extends Error {
  readonly status: number
  readonly payload: unknown

  constructor(status: number, payload: unknown) {
    const detail =
      payload && typeof payload === "object" && "detail" in payload
        ? String((payload as { detail: unknown }).detail)
        : `The request failed with status ${status}.`
    super(detail)
    this.name = "EditorRequestFailed"
    this.status = status
    this.payload = payload
  }
}

export interface EditorClientOptions {
  /** Where the authoring URLs are included, e.g. `/api/authoring/`. */
  baseUrl: string
  /** Headers every call carries -- a CSRF token, an Authorization header. */
  headers?: Record<string, string> | (() => Record<string, string>)
  /** Passed through to `fetch`; `"same-origin"` by default, for the cookie. */
  credentials?: RequestCredentials
  fetch?: typeof fetch
}

const JSON_HEADERS = { "Content-Type": "application/json", Accept: "application/json" }

export function createEditorClient(options: EditorClientOptions): AuthoringApi {
  const base = options.baseUrl.endsWith("/") ? options.baseUrl : `${options.baseUrl}/`
  const doFetch = options.fetch ?? globalThis.fetch
  const headersOf = () =>
    typeof options.headers === "function" ? options.headers() : (options.headers ?? {})

  async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
    const response = await doFetch(`${base}${path}`, {
      credentials: options.credentials ?? "same-origin",
      ...init,
      headers: { ...JSON_HEADERS, ...headersOf(), ...(init.headers ?? {}) },
    })
    const payload = await readBody(response)
    if (response.status === 422 && isIssueList(payload)) {
      throw new DefinitionRejected(payload.issues)
    }
    if (!response.ok) throw new EditorRequestFailed(response.status, payload)
    return payload as T
  }

  const versionPath = (questionnaire: string, version: number) =>
    `questionnaires/${encodeURIComponent(questionnaire)}/versions/${version}/`

  return {
    async fetchCatalog(signal) {
      return call<EditorCatalog>("catalog/", { signal })
    },
    async fetchDefinition(questionnaire, version, signal) {
      const payload = await call<{ document: QuestionnaireDefinition }>(
        versionPath(questionnaire, version),
        { signal },
      )
      return payload.document
    },
    async saveDefinition(questionnaire, version, document, acknowledgement) {
      const payload = await call<{ document: QuestionnaireDefinition }>(
        versionPath(questionnaire, version),
        {
          method: "PUT",
          body: JSON.stringify({ document, acknowledgement: acknowledgement ?? null }),
        },
      )
      return payload.document
    },
    async forkVersion(questionnaire, version, title) {
      const payload = await call<{ document: QuestionnaireDefinition }>(
        `${versionPath(questionnaire, version)}fork/`,
        { method: "POST", body: JSON.stringify(title ? { title } : {}) },
      )
      return payload.document
    },
    async listQuestionnaires(signal) {
      const payload = await call<{ questionnaires: AuthoredQuestionnaire[] }>(
        "questionnaires/",
        { signal },
      )
      return payload.questionnaires
    },
    async createQuestionnaire(input) {
      const payload = await call<{ document: QuestionnaireDefinition }>("questionnaires/new/", {
        method: "POST",
        body: JSON.stringify(input),
      })
      return payload.document
    },
    async deleteQuestionnaire(questionnaire) {
      await call<null>(`questionnaires/${encodeURIComponent(questionnaire)}/`, {
        method: "DELETE",
      })
    },
    async deleteVersion(questionnaire, version) {
      await call<null>(versionPath(questionnaire, version), { method: "DELETE" })
    },
    async listResponses(query, signal) {
      return call<ResponsePage>(`responses/?${responseQueryString(query)}`, { signal })
    },
    responseExportUrl(query) {
      return `${base}responses/export/?${responseQueryString(query)}`
    },
  }
}

async function readBody(response: Response): Promise<unknown> {
  const text = await response.text()
  if (!text) return null
  try {
    return JSON.parse(text)
  } catch {
    return { detail: text }
  }
}

function isIssueList(payload: unknown): payload is { issues: DefinitionIssue[] } {
  return (
    !!payload &&
    typeof payload === "object" &&
    Array.isArray((payload as { issues?: unknown }).issues)
  )
}
