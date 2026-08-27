/**
 * The client half of the validators this project registered in Python.
 *
 * The key is the contract: `business_email` is registered under the same
 * string on both sides, so the browser refuses a personal address without
 * asking the server. `unique_company_name` is marked server-only in Python and
 * has no counterpart here on purpose -- the browser cannot know what other
 * responses said, and the diagnostics panel shows it saying so.
 */

import { registerClientValidator } from "@vintasoftware/django-questionnaires"

const FREE_PROVIDERS = new Set([
  "gmail.com",
  "hotmail.com",
  "outlook.com",
  "yahoo.com",
  "icloud.com",
  "proton.me",
])

let registered = false

export function registerClientValidators(): void {
  if (registered) return
  registered = true

  registerClientValidator("business_email", {
    validate(value, _params, ctx) {
      if (typeof value !== "string" || !value.includes("@")) return ctx.fail("invalid_type")
      const domain = value.split("@").pop()?.toLowerCase() ?? ""
      if (FREE_PROVIDERS.has(domain)) ctx.fail("personal_address", { domain })
    },
  })
}
