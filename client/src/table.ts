/**
 * Responses as a table, as emitted by `vinta_django_questionnaires.reporting`.
 *
 * The columns come back with the rows, because what a questionnaire asks is
 * not something a client can know in advance -- and because the same list
 * drives the CSV export, so what is on screen and what is downloaded are the
 * same thing.
 */

export interface ResponseColumn {
  key: string
  label: string
  /** `meta` for something about the response, `answer` for a question. */
  group: "meta" | "answer"
  /** Where the question sits, for grouping a column picker. */
  page: string
  section: string
  questionType: string
}

export interface ResponseRow {
  [key: string]: unknown
}

export interface ResponsePage {
  columns: ResponseColumn[]
  /** What this reply's rows actually hold, in order. */
  selectedColumns: string[]
  /** A sensible first view, for a client with nothing stored. */
  defaultColumns: string[]
  results: ResponseRow[]
  page: number
  pageSize: number
  total: number
  totalPages: number
}

export interface ResponseQuery {
  questionnaire?: string
  version?: number
  status?: string
  search?: string
  page?: number
  pageSize?: number
  /** Which columns the rows should hold. Empty means all of them. */
  columns?: string[]
}

/** A response query as the query string both endpoints read. */
export function responseQueryString(query: ResponseQuery): string {
  const params = new URLSearchParams()
  if (query.questionnaire) params.set("questionnaire", query.questionnaire)
  if (query.version !== undefined) params.set("version", String(query.version))
  if (query.status) params.set("status", query.status)
  if (query.search) params.set("search", query.search)
  if (query.page !== undefined) params.set("page", String(query.page))
  if (query.pageSize !== undefined) params.set("pageSize", String(query.pageSize))
  if (query.columns?.length) params.set("columns", query.columns.join(","))
  return params.toString()
}

/** One cell as text, the same way the CSV export renders it. */
export function cellText(value: unknown): string {
  if (value === null || value === undefined) return ""
  if (typeof value === "boolean") return value ? "true" : "false"
  if (typeof value === "string" || typeof value === "number") return String(value)
  if (Array.isArray(value) && value.every((entry) => typeof entry !== "object")) {
    return value.map((entry) => String(entry)).join(", ")
  }
  return JSON.stringify(value)
}

/** The columns grouped the way a picker wants them: metadata, then by page. */
export function groupColumns(
  columns: readonly ResponseColumn[],
): { title: string; columns: ResponseColumn[] }[] {
  const groups = new Map<string, ResponseColumn[]>()
  for (const column of columns) {
    const title = column.group === "meta" ? "The response" : column.page || "Questions"
    groups.set(title, [...(groups.get(title) ?? []), column])
  }
  return [...groups].map(([title, entries]) => ({ title, columns: entries }))
}
