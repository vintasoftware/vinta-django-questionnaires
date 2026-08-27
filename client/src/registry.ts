/**
 * Client-side implementations of custom validators.
 *
 * The key is the same string the Python class registers under -- that shared
 * identity is the whole contract:
 *
 * ```ts
 * registerClientValidator("is_company_domain", {
 *   validate(value, params, ctx) {
 *     if (typeof value === "string" && !value.endsWith(`@${params.domain}`)) {
 *       ctx.fail("foreign_domain")
 *     }
 *   },
 * })
 * ```
 *
 * A plan naming a validator nobody registered is skipped and reported through
 * `onDiagnostic`; the server still enforces it on save.
 */

import type { ValidationContext } from "./context.js"

export interface CustomRunContext {
  /** Report one of the validator's declared error keys. */
  fail(errorKey: string, params?: Record<string, unknown>): void
  /** What the earlier links of the chain recorded. */
  chain: ValidationContext
}

export interface ClientValidator {
  validate(
    value: unknown,
    params: Record<string, unknown>,
    context: CustomRunContext,
  ): { data?: Record<string, unknown> } | void
}

const validators = new Map<string, ClientValidator>()

export function registerClientValidator(key: string, validator: ClientValidator): void {
  validators.set(key, validator)
}

export function unregisterClientValidator(key: string): void {
  validators.delete(key)
}

export function getClientValidator(key: string): ClientValidator | undefined {
  return validators.get(key)
}

export function registeredValidatorKeys(): string[] {
  return [...validators.keys()].sort()
}
