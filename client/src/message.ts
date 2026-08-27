/**
 * Message formatting, matching `BaseValidator.message_for` exactly.
 *
 * Python formats with `str.format` and falls back to the raw template when a
 * placeholder has no value.  So does this: a half-substituted message would be
 * worse than an honest one.
 */

const PLACEHOLDER = /\{([A-Za-z_][A-Za-z0-9_]*)\}/g

export function formatMessage(template: string, params: Record<string, unknown>): string {
  let missing = false
  const formatted = template.replace(PLACEHOLDER, (match, name: string) => {
    if (!(name in params) || params[name] === undefined) {
      missing = true
      return match
    }
    return stringify(params[name])
  })
  return missing ? template : formatted
}

function stringify(value: unknown): string {
  if (value === null) return "None"
  if (typeof value === "string") return value
  if (Array.isArray(value) || typeof value === "object") return JSON.stringify(value)
  return String(value)
}
