/**
 * The whole flow: open a response, fill in the page you are on, push it.
 *
 * The interesting part is how little of this is about validation. The plan the
 * server sends carries the rules, `buildPageSchema` turns them into a Zod
 * schema, and the same rules run again on submit -- so what is left here is
 * rendering.
 */

import { useEffect, useMemo, useRef, useState } from "react"

import { Link } from "@tanstack/react-router"

import {
  applicablePageQuestions,
  buildPageSchema,
  onDiagnostic,
  type Diagnostic,
  type PagePlan,
  type QuestionPlan,
  type QuestionnaireResponsePayload,
} from "@vintasoftware/django-questionnaires"
import { Alert, AlertDescription, AlertTitle } from "vinta-schedule-design-system/ui/alert"
import { Button } from "vinta-schedule-design-system/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "vinta-schedule-design-system/ui/card"
import { Spinner } from "vinta-schedule-design-system/ui/spinner"
import {
  Container,
  Grid,
  GridItem,
  HStack,
  Heading,
  PageHeader,
  Text,
  VStack,
} from "vinta-schedule-design-system/layout"

import { ApiError, bootstrap, openResponse, readResponse, skipPage, submitPage, valueSetOptions } from "../api"
import { responsive, type WindowSizeRange } from "../breakpoints"
import { registerClientValidators } from "../validators"
import { DiagnosticsPanel } from "./DiagnosticsPanel"
import { ProgressPanel } from "./ProgressPanel"
import { QuestionField } from "./QuestionField"

const QUESTIONNAIRE = "client-onboarding"
const STORAGE_KEY = "questionnaires-demo-response"

type Errors = Record<string, string[]>

export function Questionnaire() {
  const [response, setResponse] = useState<QuestionnaireResponsePayload | null>(null)
  const [values, setValues] = useState<Record<string, unknown>>({})
  const [errors, setErrors] = useState<Errors>({})
  const [diagnostics, setDiagnostics] = useState<Diagnostic[]>([])
  const [options, setOptions] = useState<Record<string, { value: string; label: string }[]>>({})
  const [failure, setFailure] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const validateEagerly = useRef(false)

  useEffect(() => {
    registerClientValidators()
    return onDiagnostic((diagnostic) => setDiagnostics((all) => [...all, diagnostic]))
  }, [])

  useEffect(() => {
    let cancelled = false
    async function start() {
      await bootstrap()
      const saved = localStorage.getItem(STORAGE_KEY)
      const payload = saved
        ? await readResponse(saved).catch(() => openResponse(QUESTIONNAIRE))
        : await openResponse(QUESTIONNAIRE)
      if (cancelled) return
      localStorage.setItem(STORAGE_KEY, payload.id)
      setResponse(payload)
    }
    start().catch((error: Error) => setFailure(error.message))
    return () => {
      cancelled = true
    }
  }, [])

  const plan = response?.plan
  const page = plan?.pages.find((entry) => entry.key === response?.progress.current)
  const ranges = (plan?.windowSizeRanges ?? []) as WindowSizeRange[]

  // The answers as they will stand once this page lands -- the same merge the
  // server does before it decides what the page is asking.
  const document = useMemo(
    () => ({ ...(response?.answers ?? {}), ...values }),
    [response?.answers, values],
  )
  const asked = useMemo(
    () => (page ? applicablePageQuestions(page, document) : []),
    [page, document],
  )

  useEffect(() => {
    setValues(seedValues(page, response?.answers ?? {}))
    setErrors({})
    validateEagerly.current = false
  }, [page?.key, response?.answers])

  useEffect(() => {
    for (const question of asked) {
      const key = question.valueSet?.key
      if (!key || options[key] || question.valueSet?.resolvedByTheClient) continue
      valueSetOptions(key)
        .then((payload) => setOptions((all) => ({ ...all, [key]: payload.options ?? [] })))
        .catch(() => setOptions((all) => ({ ...all, [key]: [] })))
    }
  }, [asked, options])

  function change(question: QuestionPlan, value: unknown) {
    const next = { ...values, [question.key]: value }
    setValues(next)
    if (validateEagerly.current && page && response) {
      setErrors(validate(page, next, response))
    }
  }

  async function submit() {
    if (!page || !response) return
    validateEagerly.current = true
    const found = validate(page, values, response)
    setErrors(found)
    if (Object.keys(found).length > 0) return

    setBusy(true)
    setFailure(null)
    try {
      const result = await submitPage(response.id, page.key, values)
      setResponse({ ...result.response, plan: response.plan })
    } catch (error) {
      if (error instanceof ApiError && error.errors) {
        setErrors(
          Object.fromEntries(
            Object.entries(error.errors).map(([key, issues]) => [
              key,
              issues.map((issue) => issue.message),
            ]),
          ),
        )
      } else if (error instanceof Error) {
        setFailure(error.message)
      }
    } finally {
      setBusy(false)
    }
  }

  async function skip() {
    if (!page || !response) return
    setBusy(true)
    try {
      const result = await skipPage(response.id, page.key)
      setResponse({ ...result.response, plan: response.plan })
    } catch (error) {
      if (error instanceof Error) setFailure(error.message)
    } finally {
      setBusy(false)
    }
  }

  function restart() {
    localStorage.removeItem(STORAGE_KEY)
    setResponse(null)
    setDiagnostics([])
    openResponse(QUESTIONNAIRE)
      .then((payload) => {
        localStorage.setItem(STORAGE_KEY, payload.id)
        setResponse(payload)
      })
      .catch((error: Error) => setFailure(error.message))
  }

  if (failure && !response) {
    return (
      <Container width="prose" py={10}>
        <Alert variant="destructive">
          <AlertTitle>Could not reach the questionnaire</AlertTitle>
          <AlertDescription>
            {failure}. Is the Django example project running on port 8000, and has
            <Text as="code"> seed_example </Text> been run?
          </AlertDescription>
        </Alert>
      </Container>
    )
  }

  if (!response || !plan) {
    return (
      <Container width="prose" py={10}>
        <HStack gap={3} align="center">
          <Spinner />
          <Text color="muted-foreground">Opening a response…</Text>
        </HStack>
      </Container>
    )
  }

  return (
    <Container py={8}>
      <VStack gap={6}>
        <PageHeader
          title={plan.title ?? plan.questionnaire}
          description={`Version ${plan.version} · ${response.policy.editPolicy.replace("_", " ")}`}
          actions={
            <HStack gap={2}>
              <Button variant="outline" asChild>
                <Link to="/login">Back office</Link>
              </Button>
              <Button variant="outline" onClick={restart}>
                Start over
              </Button>
            </HStack>
          }
        />

        <Grid columns={{ base: 1, lg: 3 }} gap={6}>
          <GridItem span={{ base: 1, lg: 2 }}>
            {page ? (
              <Card>
                <CardHeader>
                  <CardTitle>{page.title ?? page.key}</CardTitle>
                  {page.description ? <Text color="muted-foreground">{page.description}</Text> : null}
                </CardHeader>
                <CardContent>
                  <VStack gap={8}>
                    {page.sections.map((section) => {
                      const sectionQuestions = asked.filter((question) =>
                        section.questions.some((entry) => entry.key === question.key),
                      )
                      if (sectionQuestions.length === 0) return null
                      return (
                        <VStack key={section.key} gap={4}>
                          <VStack gap={1}>
                            <Heading level={3}>{section.title ?? section.key}</Heading>
                            {section.description ? (
                              <Text size="sm" color="muted-foreground">
                                {section.description}
                              </Text>
                            ) : null}
                          </VStack>
                          <Grid columns={responsive(section.columns, ranges)} gap={5}>
                            {sectionQuestions.map((question) => (
                              <GridItem
                                key={question.key}
                                span={responsive(question.minimumColumns, ranges)}
                                style={{
                                  ...(question.requiresBeingFirstInARow
                                    ? { gridColumnStart: 1 }
                                    : {}),
                                  ...(question.requiresBeingLastInARow
                                    ? { gridColumnEnd: -1 }
                                    : {}),
                                }}
                              >
                                <QuestionField
                                  question={question}
                                  value={values[question.key]}
                                  onChange={(value) => change(question, value)}
                                  errors={errors[question.key] ?? []}
                                  options={
                                    question.valueSet
                                      ? (options[question.valueSet.key] ?? [])
                                      : undefined
                                  }
                                  optionsPending={
                                    !!question.valueSet && !options[question.valueSet.key]
                                  }
                                />
                              </GridItem>
                            ))}
                          </Grid>
                          {section.conclusion ? (
                            <Text size="sm" color="muted-foreground">
                              {section.conclusion}
                            </Text>
                          ) : null}
                        </VStack>
                      )
                    })}

                    {failure ? (
                      <Alert variant="destructive">
                        <AlertDescription>{failure}</AlertDescription>
                      </Alert>
                    ) : null}

                    <HStack gap={3} justify="end">
                      {page.isSkippable ? (
                        <Button variant="ghost" onClick={skip} disabled={busy}>
                          Skip for now
                        </Button>
                      ) : null}
                      <Button onClick={submit} disabled={busy}>
                        {busy ? "Sending…" : "Continue"}
                      </Button>
                    </HStack>
                  </VStack>
                </CardContent>
              </Card>
            ) : (
              <Card>
                <CardHeader>
                  <CardTitle>All done</CardTitle>
                </CardHeader>
                <CardContent>
                  <VStack gap={4}>
                    <Text color="muted-foreground">
                      Every page that applies has been filled in. The response is
                      {" "}{response.status.replace("_", " ")}.
                    </Text>
                    <Text as="pre" size="sm">
                      {JSON.stringify(response.answers, null, 2)}
                    </Text>
                  </VStack>
                </CardContent>
              </Card>
            )}
          </GridItem>

          <GridItem>
            <VStack gap={6}>
              <ProgressPanel plan={plan} progress={response.progress} />
              <DiagnosticsPanel diagnostics={diagnostics} />
            </VStack>
          </GridItem>
        </Grid>
      </VStack>
    </Container>
  )
}

function seedValues(page: PagePlan | undefined, answers: Record<string, unknown>) {
  if (!page) return {}
  const keys = page.sections.flatMap((section) => section.questions.map((entry) => entry.key))
  return Object.fromEntries(
    keys.filter((key) => key in answers).map((key) => [key, answers[key]]),
  )
}

/** The client half of the check: the same rules, before the round trip. */
function validate(
  page: PagePlan,
  values: Record<string, unknown>,
  response: QuestionnaireResponsePayload,
): Errors {
  const schema = buildPageSchema(page, { answers: response.answers })
  const result = schema.safeParse(values)
  if (result.success) return {}
  const found: Errors = {}
  for (const issue of result.error.issues) {
    const key = String(issue.path[0] ?? "")
    found[key] = [...(found[key] ?? []), issue.message]
  }
  return found
}
