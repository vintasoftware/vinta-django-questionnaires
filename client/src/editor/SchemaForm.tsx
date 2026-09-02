/**
 * A form for a JSON Schema object -- a validator's params, a widget's props.
 *
 * Neither of those is fixed: a validator another app registers brings its own
 * params schema, and a widget's props are whatever its component takes. So the
 * editor renders the schema rather than a form per validator, and falls back to
 * a JSON field for anything it does not recognise, which is always correct even
 * when it is not pretty.
 */

import { useEffect, useState } from "react"

import { Checkbox, NumberInput, Select, TextArea, TextInput } from "./fields.js"
import { useStrings, type WithStrings } from "./strings.js"
import type { Translate } from "../strings.js"

interface Schema {
  type?: string | string[]
  properties?: Record<string, Schema>
  required?: string[]
  enum?: unknown[]
  title?: string
  description?: string
  items?: Schema
  default?: unknown
}

export interface SchemaFormProps extends WithStrings {
  schema: Record<string, unknown> | null | undefined
  value: Record<string, unknown>
  onChange: (value: Record<string, unknown>) => void
  errors?: string[]
  /** Shown above the fields when the schema has any. */
  label: string
}

export function SchemaForm({
  schema,
  value,
  onChange,
  errors,
  label,
  strings,
}: SchemaFormProps) {
  const t = useStrings(strings)
  const parsed = (schema ?? {}) as Schema
  const properties = parsed.properties ?? {}
  const names = Object.keys(properties)

  if (!names.length) {
    return (
      <JsonField
        label={label}
        value={value}
        onChange={(next) => onChange((next ?? {}) as Record<string, unknown>)}
        errors={errors}
        hint={t("schemaForm.jsonOnly")}
      />
    )
  }

  const required = new Set(parsed.required ?? [])
  return (
    <fieldset className="vqe-fieldset">
      <legend className="vqe-fieldset__legend">{label}</legend>
      {names.map((name) => (
        <SchemaField
          key={name}
          t={t}
          name={name}
          schema={properties[name] as Schema}
          required={required.has(name)}
          value={value[name]}
          onChange={(next) => {
            const updated = { ...value }
            if (next === undefined) delete updated[name]
            else updated[name] = next
            onChange(updated)
          }}
        />
      ))}
      {errors?.length ? (
        <ul className="vqe-errors">
          {errors.map((message, index) => (
            <li key={index}>{message}</li>
          ))}
        </ul>
      ) : null}
    </fieldset>
  )
}

function SchemaField({
  t,
  name,
  schema,
  required,
  value,
  onChange,
}: {
  t: Translate
  name: string
  schema: Schema
  required: boolean
  value: unknown
  onChange: (value: unknown) => void
}) {
  const own = schema.title ?? name
  const label = required ? t("schemaForm.required", { label: own }) : own
  const hint = schema.description
  const kind = Array.isArray(schema.type) ? schema.type[0] : schema.type

  if (schema.enum) {
    return (
      <Select
        label={label}
        hint={hint}
        value={value === undefined || value === null ? "" : String(value)}
        emptyLabel={required ? undefined : t("field.empty")}
        options={schema.enum.map((entry) => ({ value: String(entry), label: String(entry) }))}
        onChange={(next) => onChange(next === "" ? undefined : next)}
      />
    )
  }
  if (kind === "boolean") {
    return <Checkbox label={label} hint={hint} checked={!!value} onChange={onChange} />
  }
  if (kind === "number" || kind === "integer") {
    return (
      <NumberInput
        label={label}
        hint={hint}
        value={typeof value === "number" ? value : null}
        onChange={(next) => onChange(next === null ? undefined : next)}
      />
    )
  }
  if (kind === "string") {
    return (
      <TextInput
        label={label}
        hint={hint}
        value={typeof value === "string" ? value : ""}
        onChange={(next) => onChange(next === "" ? undefined : next)}
      />
    )
  }
  return (
    <JsonField
      label={label}
      hint={hint ?? t("schemaForm.jsonHint")}
      value={value}
      onChange={onChange}
    />
  )
}

export interface JsonFieldProps extends WithStrings {
  label: string
  value: unknown
  onChange: (value: unknown) => void
  hint?: string
  errors?: string[]
  rows?: number
}

/**
 * A JSON value as text.
 *
 * The text is held locally while it is being typed, because half-written JSON
 * does not parse and losing what someone is in the middle of writing is worse
 * than showing them a parse error.
 */
export function JsonField({
  label,
  value,
  onChange,
  hint,
  errors,
  rows = 4,
  strings,
}: JsonFieldProps) {
  const t = useStrings(strings)
  const serialised = value === undefined ? "" : JSON.stringify(value, null, 2)
  const [text, setText] = useState(serialised)
  const [parseError, setParseError] = useState<string | null>(null)

  useEffect(() => {
    // Only follow the outside when it genuinely differs from what is typed, so
    // reformatting does not fight the cursor.
    setText((current) => {
      try {
        if (JSON.stringify(JSON.parse(current || "null")) === JSON.stringify(value ?? null)) {
          return current
        }
      } catch {
        return current
      }
      return serialised
    })
  }, [serialised, value])

  return (
    <TextArea
      label={label}
      hint={hint}
      rows={rows}
      monospace
      errors={parseError ? [parseError, ...(errors ?? [])] : errors}
      value={text}
      onChange={(next) => {
        setText(next)
        if (next.trim() === "") {
          setParseError(null)
          onChange(undefined)
          return
        }
        try {
          const parsed = JSON.parse(next)
          setParseError(null)
          onChange(parsed)
        } catch (error) {
          setParseError(error instanceof Error ? error.message : t("schemaForm.invalidJson"))
        }
      }}
    />
  )
}
