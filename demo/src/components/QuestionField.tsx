/**
 * One question, rendered with the design system.
 *
 * Which component to use comes from the plan: the widget key the server
 * resolved is a design system component name, and the widget props are that
 * component's props, so they are spread on as they arrive.
 */

import type { QuestionPlan } from "@vintasoftware/django-questionnaires"
import { Alert, AlertDescription } from "vinta-schedule-design-system/ui/alert"
import { Badge } from "vinta-schedule-design-system/ui/badge"
import { Button } from "vinta-schedule-design-system/ui/button"
import { Card, CardContent } from "vinta-schedule-design-system/ui/card"
import { Checkbox } from "vinta-schedule-design-system/ui/checkbox"
import { Combobox } from "vinta-schedule-design-system/ui/combobox"
import { Input } from "vinta-schedule-design-system/ui/input"
import { Label } from "vinta-schedule-design-system/ui/label"
import { RadioGroup, RadioGroupItem } from "vinta-schedule-design-system/ui/radio-group"
import { Textarea } from "vinta-schedule-design-system/ui/textarea"
import { Grid, HStack, Text, VStack } from "vinta-schedule-design-system/layout"

export interface FieldProps {
  question: QuestionPlan
  value: unknown
  onChange: (value: unknown) => void
  errors: string[]
  options?: { value: string; label: string }[]
  optionsPending?: boolean
}

const OTHER = "__other__"

export function QuestionField(props: FieldProps) {
  const { question, errors } = props
  const id = `q-${question.key}`
  return (
    <VStack gap={2}>
      <HStack gap={2} align="center">
        <Label htmlFor={id}>{question.title}</Label>
        {question.checks.some((check) => check.validator === "required") ? (
          <Badge variant="secondary">Required</Badge>
        ) : null}
        {question.checks.some((check) => "serverOnly" in check && check.serverOnly) ? (
          <Badge variant="outline">Checked on submit</Badge>
        ) : null}
      </HStack>
      {question.description ? (
        <Text size="sm" color="muted-foreground">
          {question.description}
        </Text>
      ) : null}
      <Control {...props} id={id} />
      {errors.map((message) => (
        <Alert key={message} variant="destructive">
          <AlertDescription>{message}</AlertDescription>
        </Alert>
      ))}
    </VStack>
  )
}

function Control({ question, value, onChange, options, optionsPending, id }: FieldProps & { id: string }) {
  const widget = question.widget ?? ""
  const widgetProps = (question.widgetProps ?? {}) as Record<string, never>

  switch (widget) {
    case "textarea":
      return (
        <Textarea
          id={id}
          {...widgetProps}
          value={(value as string) ?? ""}
          onChange={(event) => onChange(event.target.value)}
        />
      )

    case "radio-group": {
      const { orientation, ...rest } = widgetProps as { orientation?: string }
      return (
        <RadioGroup
          {...rest}
          id={id}
          value={(value as string) ?? ""}
          onValueChange={onChange}
          className={orientation === "horizontal" ? "flex flex-row gap-6" : undefined}
        >
          {(question.choices ?? []).map((choice) => (
            <HStack key={choice.value} gap={2} align="center">
              <RadioGroupItem value={choice.value} id={`${id}-${choice.value}`} />
              <Label htmlFor={`${id}-${choice.value}`}>{choice.label}</Label>
            </HStack>
          ))}
        </RadioGroup>
      )
    }

    case "checkbox-group": {
      const selected = Array.isArray(value) ? (value as string[]) : []
      const { columns } = widgetProps as { columns?: number }
      return (
        <Grid columns={{ base: 1, md: columns ?? 1 }} gap={2}>
          {(question.choices ?? []).map((choice) => (
            <HStack key={choice.value} gap={2} align="center">
              <Checkbox
                id={`${id}-${choice.value}`}
                checked={selected.includes(choice.value)}
                onCheckedChange={(checked) =>
                  onChange(
                    checked
                      ? [...selected, choice.value]
                      : selected.filter((entry) => entry !== choice.value),
                  )
                }
              />
              <Label htmlFor={`${id}-${choice.value}`}>{choice.label}</Label>
            </HStack>
          ))}
          {question.allowsOther ? (
            <HStack key={OTHER} gap={2} align="center">
              <Checkbox
                id={`${id}-other`}
                checked={selected.includes(OTHER)}
                onCheckedChange={(checked) =>
                  onChange(
                    checked ? [...selected, OTHER] : selected.filter((entry) => entry !== OTHER),
                  )
                }
              />
              <Label htmlFor={`${id}-other`}>Something else</Label>
            </HStack>
          ) : null}
        </Grid>
      )
    }

    case "combobox": {
      const isMultiple = question.type === "multi_select"
      const shared = {
        ...(widgetProps as { placeholder?: string; searchPlaceholder?: string; emptyText?: string }),
        id,
        options: options ?? [],
        isLoading: optionsPending ?? false,
      }
      return isMultiple ? (
        <Combobox
          {...shared}
          multiple
          value={Array.isArray(value) ? (value as string[]) : []}
          onValueChange={(next) => onChange(next)}
        />
      ) : (
        <Combobox {...shared} value={(value as string) ?? ""} onValueChange={onChange} />
      )
    }

    case "number-input": {
      const { prefix, step } = widgetProps as { prefix?: string; step?: number }
      return (
        <HStack gap={2} align="center">
          {prefix ? <Text color="muted-foreground">{prefix}</Text> : null}
          <Input
            id={id}
            type="number"
            step={step}
            value={value === null || value === undefined ? "" : String(value)}
            onChange={(event) =>
              onChange(event.target.value === "" ? null : Number(event.target.value))
            }
          />
        </HStack>
      )
    }

    case "date-range": {
      const { startLabel, endLabel } = widgetProps as { startLabel?: string; endLabel?: string }
      const range = (value ?? {}) as { start?: string; end?: string }
      return (
        <Grid columns={{ base: 1, md: 2 }} gap={3}>
          <VStack gap={1}>
            <Label htmlFor={`${id}-start`}>{startLabel ?? "From"}</Label>
            <Input
              id={`${id}-start`}
              type="date"
              value={range.start ?? ""}
              onChange={(event) => onChange({ ...range, start: event.target.value || null })}
            />
          </VStack>
          <VStack gap={1}>
            <Label htmlFor={`${id}-end`}>{endLabel ?? "Until"}</Label>
            <Input
              id={`${id}-end`}
              type="date"
              value={range.end ?? ""}
              onChange={(event) => onChange({ ...range, end: event.target.value || null })}
            />
          </VStack>
        </Grid>
      )
    }

    case "file-upload": {
      const file = value as { name?: string; size?: number } | null
      return (
        <VStack gap={2}>
          <Input
            id={id}
            type="file"
            {...(widgetProps as { accept?: string })}
            onChange={(event) => {
              const picked = event.target.files?.[0]
              onChange(
                picked
                  ? { name: picked.name, size: picked.size, content_type: picked.type }
                  : null,
              )
            }}
          />
          {file?.name ? (
            <Text size="sm" color="muted-foreground">
              {file.name} ({file.size} bytes) -- the demo records the file, it does not upload it.
            </Text>
          ) : null}
        </VStack>
      )
    }

    case "repeatable-group":
      return <RepeatableGroup question={question} value={value} onChange={onChange} id={id} />

    default:
      return (
        <Input
          id={id}
          {...widgetProps}
          value={(value as string) ?? ""}
          onChange={(event) => onChange(event.target.value)}
        />
      )
  }
}

function RepeatableGroup({
  question,
  value,
  onChange,
  id,
}: {
  question: QuestionPlan
  value: unknown
  onChange: (value: unknown) => void
  id: string
}) {
  const entries = Array.isArray(value) ? (value as Record<string, unknown>[]) : []
  const { addLabel, maxEntries } = (question.widgetProps ?? {}) as {
    addLabel?: string
    maxEntries?: number
  }
  const sub = question.subQuestionnaire
  const questions =
    sub && "pages" in sub
      ? sub.pages.flatMap((page) => page.sections.flatMap((section) => section.questions))
      : []

  return (
    <VStack gap={3}>
      {entries.map((entry, index) => (
        <Card key={index}>
          <CardContent>
            <VStack gap={3} p={4}>
              {questions.map((nested) => (
                <VStack key={nested.key} gap={1}>
                  <Label htmlFor={`${id}-${index}-${nested.key}`}>{nested.title}</Label>
                  {nested.choices?.length ? (
                    <RadioGroup
                      id={`${id}-${index}-${nested.key}`}
                      value={(entry[nested.key] as string) ?? ""}
                      onValueChange={(next) =>
                        onChange(
                          entries.map((other, position) =>
                            position === index ? { ...other, [nested.key]: next } : other,
                          ),
                        )
                      }
                      className="flex flex-row gap-6"
                    >
                      {nested.choices.map((choice) => (
                        <HStack key={choice.value} gap={2} align="center">
                          <RadioGroupItem
                            value={choice.value}
                            id={`${id}-${index}-${nested.key}-${choice.value}`}
                          />
                          <Label htmlFor={`${id}-${index}-${nested.key}-${choice.value}`}>
                            {choice.label}
                          </Label>
                        </HStack>
                      ))}
                    </RadioGroup>
                  ) : (
                    <Input
                      id={`${id}-${index}-${nested.key}`}
                      value={(entry[nested.key] as string) ?? ""}
                      onChange={(event) =>
                        onChange(
                          entries.map((other, position) =>
                            position === index
                              ? { ...other, [nested.key]: event.target.value }
                              : other,
                          ),
                        )
                      }
                    />
                  )}
                </VStack>
              ))}
              <HStack justify="end">
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => onChange(entries.filter((_, position) => position !== index))}
                >
                  Remove
                </Button>
              </HStack>
            </VStack>
          </CardContent>
        </Card>
      ))}
      <HStack>
        <Button
          type="button"
          variant="outline"
          disabled={maxEntries !== undefined && entries.length >= maxEntries}
          onClick={() => onChange([...entries, {}])}
        >
          {addLabel ?? "Add"}
        </Button>
      </HStack>
    </VStack>
  )
}
