/**
 * Talking to the Django example project.
 *
 * Everything goes through `/demo-api`, which Vite proxies to Django, so the
 * browser stays on one origin and the session and CSRF cookies behave the way
 * they would in production behind a single domain.
 */

import type {
  PageSubmitResult,
  QuestionnaireResponsePayload,
  ValidationErrorPayload,
} from "vinta-django-questionnaires-client"

const BASE = "/demo-api"

export interface ValueSetOptions {
  key: string
  source: string
  options?: { value: string; label: string }[]
  endpoint?: { url: string; resultsPath: string; valuePath: string; labelPath: string }
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
    readonly errors?: ValidationErrorPayload["errors"],
  ) {
    super(detail)
  }
}

export function csrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]*)/)
  return match?.[1] ? decodeURIComponent(match[1]) : ""
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    ...init,
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...(init.method && init.method !== "GET" ? { "X-CSRFToken": csrfToken() } : {}),
      ...init.headers,
    },
  })
  const body = response.status === 204 ? {} : await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new ApiError(
      response.status,
      (body as { detail?: string }).detail ?? response.statusText,
      (body as ValidationErrorPayload).errors,
    )
  }
  return body as T
}

export interface BootstrapPayload {
  questionnaires: { key: string; name: string; version: number; title: string }[]
}

/** Also what sets the CSRF cookie, so it comes first. */
export function bootstrap(): Promise<BootstrapPayload> {
  return request<BootstrapPayload>("/bootstrap/")
}

export function openResponse(questionnaire: string): Promise<QuestionnaireResponsePayload> {
  return request<QuestionnaireResponsePayload>("/responses/", {
    method: "POST",
    body: JSON.stringify({ questionnaire }),
  })
}

export function readResponse(id: string): Promise<QuestionnaireResponsePayload> {
  return request<QuestionnaireResponsePayload>(`/responses/${id}/`)
}

export function submitPage(
  id: string,
  pageKey: string,
  answers: Record<string, unknown>,
): Promise<PageSubmitResult> {
  return request<PageSubmitResult>(`/responses/${id}/pages/${pageKey}/`, {
    method: "POST",
    body: JSON.stringify({ answers }),
  })
}

export function skipPage(id: string, pageKey: string): Promise<PageSubmitResult> {
  return request<PageSubmitResult>(`/responses/${id}/pages/${pageKey}/skip/`, { method: "POST" })
}

export function valueSetOptions(key: string): Promise<ValueSetOptions> {
  return request<ValueSetOptions>(`/value-sets/${key}/options/`)
}
