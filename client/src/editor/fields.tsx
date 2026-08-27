/**
 * The small labelled inputs every form in the editor is built out of.
 *
 * They are plain elements with `vqe-` class names -- no design system, because
 * the editor has to drop into whichever one the host project already has. What
 * they do carry is the part that matters: a label bound to its control, and the
 * server's own error messages under the field that caused them.
 */

import { useId, type ReactNode } from "react"

export interface FieldProps {
  label: string
  hint?: ReactNode
  errors?: string[]
  children?: ReactNode
  id?: string
}

export function Field({ label, hint, errors, children, id }: FieldProps) {
  const describedBy = errors?.length ? `${id}-errors` : undefined
  return (
    <div className={`vqe-field${errors?.length ? " vqe-field--invalid" : ""}`}>
      <label className="vqe-field__label" htmlFor={id}>
        {label}
      </label>
      {children}
      {hint ? <p className="vqe-field__hint">{hint}</p> : null}
      <Errors errors={errors} id={describedBy} />
    </div>
  )
}

export function Errors({ errors, id }: { errors?: string[]; id?: string }) {
  if (!errors?.length) return null
  return (
    <ul className="vqe-errors" id={id}>
      {errors.map((message, index) => (
        <li key={index}>{message}</li>
      ))}
    </ul>
  )
}

export interface TextInputProps {
  label: string
  value: string
  onChange: (value: string) => void
  hint?: ReactNode
  errors?: string[]
  placeholder?: string
  monospace?: boolean
  disabled?: boolean
}

export function TextInput({
  label,
  value,
  onChange,
  hint,
  errors,
  placeholder,
  monospace,
  disabled,
}: TextInputProps) {
  const id = useId()
  return (
    <Field label={label} hint={hint} errors={errors} id={id}>
      <input
        id={id}
        className={`vqe-input${monospace ? " vqe-input--mono" : ""}`}
        value={value}
        placeholder={placeholder}
        disabled={disabled}
        aria-invalid={errors?.length ? true : undefined}
        onChange={(event) => onChange(event.target.value)}
      />
    </Field>
  )
}

export function TextArea({
  label,
  value,
  onChange,
  hint,
  errors,
  rows = 3,
  monospace,
}: TextInputProps & { rows?: number }) {
  const id = useId()
  return (
    <Field label={label} hint={hint} errors={errors} id={id}>
      <textarea
        id={id}
        className={`vqe-input vqe-textarea${monospace ? " vqe-input--mono" : ""}`}
        rows={rows}
        value={value}
        aria-invalid={errors?.length ? true : undefined}
        onChange={(event) => onChange(event.target.value)}
      />
    </Field>
  )
}

export interface NumberInputProps {
  label: string
  value: number | null
  onChange: (value: number | null) => void
  hint?: ReactNode
  errors?: string[]
  placeholder?: string
  min?: number
}

export function NumberInput({
  label,
  value,
  onChange,
  hint,
  errors,
  placeholder,
  min,
}: NumberInputProps) {
  const id = useId()
  return (
    <Field label={label} hint={hint} errors={errors} id={id}>
      <input
        id={id}
        type="number"
        className="vqe-input"
        min={min}
        placeholder={placeholder}
        value={value === null ? "" : value}
        aria-invalid={errors?.length ? true : undefined}
        onChange={(event) =>
          onChange(event.target.value === "" ? null : Number(event.target.value))
        }
      />
    </Field>
  )
}

export interface Option {
  value: string
  label: string
}

export interface SelectProps {
  label: string
  value: string
  options: Option[]
  onChange: (value: string) => void
  hint?: ReactNode
  errors?: string[]
  /** The label of the empty option, when one is allowed. */
  emptyLabel?: string
}

export function Select({
  label,
  value,
  options,
  onChange,
  hint,
  errors,
  emptyLabel,
}: SelectProps) {
  const id = useId()
  return (
    <Field label={label} hint={hint} errors={errors} id={id}>
      <select
        id={id}
        className="vqe-input vqe-select"
        value={value}
        aria-invalid={errors?.length ? true : undefined}
        onChange={(event) => onChange(event.target.value)}
      >
        {emptyLabel === undefined ? null : <option value="">{emptyLabel}</option>}
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </Field>
  )
}

export interface CheckboxProps {
  label: string
  checked: boolean
  onChange: (checked: boolean) => void
  hint?: ReactNode
  errors?: string[]
  disabled?: boolean
}

export function Checkbox({ label, checked, onChange, hint, errors, disabled }: CheckboxProps) {
  const id = useId()
  return (
    <div
      className={`vqe-field vqe-field--inline${errors?.length ? " vqe-field--invalid" : ""}`}
    >
      <input
        id={id}
        type="checkbox"
        className="vqe-checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
      />
      <div>
        <label className="vqe-field__label" htmlFor={id}>
          {label}
        </label>
        {hint ? <p className="vqe-field__hint">{hint}</p> : null}
        <Errors errors={errors} />
      </div>
    </div>
  )
}

export function Button({
  children,
  onClick,
  variant = "plain",
  disabled,
  title,
  type = "button",
}: {
  children: ReactNode
  onClick?: () => void
  variant?: "plain" | "primary" | "danger" | "quiet"
  disabled?: boolean
  title?: string
  type?: "button" | "submit"
}) {
  return (
    <button
      type={type}
      className={`vqe-button vqe-button--${variant}`}
      onClick={onClick}
      disabled={disabled}
      title={title}
    >
      {children}
    </button>
  )
}
