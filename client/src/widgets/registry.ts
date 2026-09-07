/**
 * Which component renders a question, and how a project replaces it.
 *
 * The package ships a working component for every question type and for every
 * widget key the default widget set installs, so a questionnaire renders as
 * soon as it is fetched. None of them are meant to survive contact with a real
 * design system, and none of them have to: a host registers its own under the
 * same key and the renderer picks it up.
 *
 * ```tsx
 * registerWidget("radio-group", (props) => <MyRadioGroup {...props} />)
 * ```
 *
 * The key is the same string the `QuestionnaireWidget` row stores, which is the
 * same string the server resolved into the plan -- that shared identity is the
 * whole contract, exactly as it is for validators in `registry.ts`.
 *
 * Overrides and defaults are kept apart on purpose. Registering over a key does
 * not destroy what the package shipped, so `unregisterWidget` puts the default
 * back rather than leaving a hole.
 */

import type { ComponentType } from "react"

import type { QuestionPlan } from "../plan.js"
import type { Translate } from "../strings.js"

/** An option a widget offers, whether it came from a plan or an endpoint. */
export interface WidgetOption {
  value: string
  label: string
}

/** What every widget component is handed. */
export interface WidgetProps {
  question: QuestionPlan
  value: unknown
  onChange: (value: unknown) => void
  /** The id the label points at. A widget with several controls suffixes it. */
  id: string
  /** What failed, already phrased by the server or by the local checks. */
  errors: readonly string[]
  disabled?: boolean
  readOnly?: boolean
  /**
   * The options to offer, for a question whose value set the client resolves.
   * A question with inline choices has them on `question.choices` instead.
   */
  options?: readonly WidgetOption[]
  optionsPending?: boolean
  /** The catalogue in force, so a widget's own words are translated too. */
  t: Translate
}

export type WidgetComponent = ComponentType<WidgetProps>

const defaults = new Map<string, WidgetComponent>()
const overrides = new Map<string, WidgetComponent>()

/**
 * Claim *key* for *component*.
 *
 * Called by a host to replace what the package ships, and by the package itself
 * -- through `registerDefaultWidget` -- to put the defaults in place.
 */
export function registerWidget(key: string, component: WidgetComponent): void {
  overrides.set(key, component)
}

/** Register what the package ships. A host's own registration still wins. */
export function registerDefaultWidget(key: string, component: WidgetComponent): void {
  defaults.set(key, component)
}

/** Drop a host's registration for *key*, leaving the package's default. */
export function unregisterWidget(key: string): void {
  overrides.delete(key)
}

/** Whatever renders *key* now: the host's, then the package's, then nothing. */
export function getWidget(key: string): WidgetComponent | undefined {
  return overrides.get(key) ?? defaults.get(key)
}

/** Whether *key* is rendered by something a host registered rather than a default. */
export function isOverridden(key: string): boolean {
  return overrides.has(key)
}

/** Every key that renders, defaults and overrides alike. */
export function registeredWidgetKeys(): string[] {
  return [...new Set([...defaults.keys(), ...overrides.keys()])].sort()
}

/** Forget every override. For tests, and for a host tearing itself down. */
export function resetWidgetOverrides(): void {
  overrides.clear()
}

/**
 * The component for *question*: its widget, then its type, then a fallback.
 *
 * The fall through the question type is what keeps a questionnaire renderable
 * before anybody installs a widget set -- a `free_text` question with no widget
 * resolved still lands on the text input registered under `free_text`.
 */
export function resolveWidget(question: QuestionPlan): WidgetComponent | undefined {
  return (question.widget ? getWidget(question.widget) : undefined) ?? getWidget(question.type)
}
