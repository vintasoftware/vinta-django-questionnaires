/**
 * Where the client reports what it could not do.
 *
 * A plan can name a validator this build has no implementation for -- someone
 * added it on the server and the frontend has not shipped yet.  The respondent
 * must not be blocked by that, and the team must not find out months later, so
 * the check is skipped (the server still enforces it) and a diagnostic is
 * emitted for whatever the host app wants to do with it:
 *
 * ```ts
 * onDiagnostic((diagnostic) => Sentry.captureMessage(diagnostic.message, {
 *   level: "warning",
 *   tags: { code: diagnostic.code, validator: diagnostic.validator },
 * }))
 * ```
 */

export type DiagnosticCode =
  "missing-validator" | "unknown-check" | "server-only" | "condition-error" | "plan-version"

export interface Diagnostic {
  code: DiagnosticCode
  message: string
  validator?: string
  kind?: string
  questionKey?: string
}

export type DiagnosticReporter = (diagnostic: Diagnostic) => void

const reporters = new Set<DiagnosticReporter>()
const alreadyReported = new Set<string>()

/** Warn once per distinct problem, so a re-render does not flood the console. */
export const consoleReporter: DiagnosticReporter = (diagnostic) => {
  // A server-only validator is a configuration, not a problem: subscribers
  // still hear about it, the console does not.
  if (diagnostic.code === "server-only") return
  // eslint-disable-next-line no-console
  console.warn(`[questionnaires] ${diagnostic.message}`)
}

let fallback: DiagnosticReporter | null = consoleReporter

/** Subscribe to diagnostics.  Returns the unsubscribe function. */
export function onDiagnostic(reporter: DiagnosticReporter): () => void {
  reporters.add(reporter)
  return () => reporters.delete(reporter)
}

/** Replace the console warning used when nothing is subscribed. */
export function setFallbackReporter(reporter: DiagnosticReporter | null): void {
  fallback = reporter
}

export function report(diagnostic: Diagnostic, extra?: DiagnosticReporter): void {
  const signature = [
    diagnostic.code,
    diagnostic.validator,
    diagnostic.kind,
    diagnostic.questionKey,
  ].join(":")
  if (alreadyReported.has(signature)) return
  alreadyReported.add(signature)

  extra?.(diagnostic)
  for (const reporter of reporters) reporter(diagnostic)
  if (reporters.size === 0 && !extra) fallback?.(diagnostic)
}

/** Forget what has already been reported.  Tests use this. */
export function resetDiagnostics(): void {
  alreadyReported.clear()
}
