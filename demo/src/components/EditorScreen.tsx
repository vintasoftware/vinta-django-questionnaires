/**
 * The authoring side of the demo: pick a version, edit it, save it.
 *
 * The editor itself comes from the package and is not restyled here on
 * purpose. What is worth showing is that it drops in whole, next to a form
 * built out of a completely different design system, and that the two agree
 * because they read the same server.
 *
 * Around it is the rest of the back office the package's authoring API
 * offers -- create a questionnaire, delete a draft, fork a live version -- so
 * the whole lifecycle is reachable without the Django admin.
 */

import { useCallback, useEffect, useState } from "react"

import { Link } from "@tanstack/react-router"
import type { AuthoredQuestionnaire } from "vinta-django-questionnaires-client"
import { QuestionnaireEditor } from "vinta-django-questionnaires-client/editor"
import { Alert, AlertDescription, AlertTitle } from "vinta-schedule-design-system/ui/alert"
import { Button } from "vinta-schedule-design-system/ui/button"
import { Card, CardContent } from "vinta-schedule-design-system/ui/card"
import { Input } from "vinta-schedule-design-system/ui/input"
import { Label } from "vinta-schedule-design-system/ui/label"
import { Container, HStack, PageHeader, Text, VStack } from "vinta-schedule-design-system/layout"

import { useSession } from "../auth"
import { editorApi } from "../editorApi"

interface Target {
  questionnaire: string
  version: number
}

export function EditorScreen() {
  const { signOut } = useSession()
  const [questionnaires, setQuestionnaires] = useState<AuthoredQuestionnaire[]>([])
  const [target, setTarget] = useState<Target | null>(null)
  const [failure, setFailure] = useState<string | null>(null)
  const [newKey, setNewKey] = useState("")
  const [newName, setNewName] = useState("")
  const [isBusy, setIsBusy] = useState(false)

  /** Re-read the list. Pass a target to select one, `null` to pick what is left. */
  const refresh = useCallback(async (select?: Target | null) => {
    const found = await editorApi.listQuestionnaires()
    setQuestionnaires(found)
    if (select !== undefined) {
      setTarget(select)
      return
    }
    setTarget((current) => {
      const stillThere = found.some(
        (entry) =>
          entry.key === current?.questionnaire &&
          entry.versions.some((version) => version.version === current.version),
      )
      if (current && stillThere) return current
      const first = found.find((entry) => entry.versions.length)
      return first?.versions[0]
        ? { questionnaire: first.key, version: first.versions[0].version }
        : null
    })
  }, [])

  const attempt = useCallback(async (work: () => Promise<unknown>) => {
    setIsBusy(true)
    setFailure(null)
    try {
      await work()
    } catch (cause: unknown) {
      setFailure(describe(cause))
    } finally {
      setIsBusy(false)
    }
  }, [])

  const create = () =>
    attempt(async () => {
      const document = await editorApi.createQuestionnaire({
        key: newKey.trim(),
        name: newName.trim() || newKey.trim(),
      })
      setNewKey("")
      setNewName("")
      await refresh({ questionnaire: document.questionnaire.key, version: document.version })
    })

  const removeVersion = () =>
    attempt(async () => {
      if (!target) return
      await editorApi.deleteVersion(target.questionnaire, target.version)
      await refresh(null)
    })

  const removeQuestionnaire = () =>
    attempt(async () => {
      if (!target) return
      await editorApi.deleteQuestionnaire(target.questionnaire)
      await refresh(null)
    })

  useEffect(() => {
    refresh().catch((cause: unknown) => setFailure(describe(cause)))
  }, [refresh])

  return (
    <Container py={8}>
      <VStack gap={6}>
        <PageHeader
          title="Questionnaire editor"
          description="The same definition the form reads, edited in place."
          actions={
            <HStack gap={2}>
              <Button variant="outline" asChild>
                <Link to="/responses">Responses</Link>
              </Button>
              <Button variant="outline" asChild>
                <Link to="/">Back to the form</Link>
              </Button>
              <Button variant="ghost" onClick={() => void signOut()}>
                Sign out
              </Button>
            </HStack>
          }
        />

        {failure ? (
          <Alert variant="destructive">
            <AlertTitle>The authoring API refused that</AlertTitle>
            <AlertDescription>{failure}</AlertDescription>
          </Alert>
        ) : null}

        <Card>
          <CardContent>
            <VStack gap={4}>
              <Text weight="medium">Version to edit</Text>
              <HStack gap={2} wrap>
                {questionnaires.flatMap((questionnaire) =>
                  questionnaire.versions.map((version) => {
                    const selected =
                      target?.questionnaire === questionnaire.key &&
                      target.version === version.version
                    return (
                      <Button
                        key={`${questionnaire.key}-${version.version}`}
                        variant={selected ? "default" : "outline"}
                        size="sm"
                        onClick={() =>
                          setTarget({
                            questionnaire: questionnaire.key,
                            version: version.version,
                          })
                        }
                      >
                        {questionnaire.name} v{version.version} · {version.status} ·{" "}
                        {version.responseCount} response(s)
                      </Button>
                    )
                  }),
                )}
                {!questionnaires.length ? (
                  <Text color="muted-foreground">Nothing to edit yet. Make one below.</Text>
                ) : null}
              </HStack>

              <HStack gap={2} wrap align="end">
                <VStack gap={1}>
                  <Label htmlFor="new-key">New questionnaire</Label>
                  <Input
                    id="new-key"
                    placeholder="key"
                    value={newKey}
                    onChange={(event) => setNewKey(event.target.value)}
                  />
                </VStack>
                <VStack gap={1}>
                  <Label htmlFor="new-name">Name</Label>
                  <Input
                    id="new-name"
                    placeholder="Name"
                    value={newName}
                    onChange={(event) => setNewName(event.target.value)}
                  />
                </VStack>
                <Button size="sm" disabled={!newKey || isBusy} onClick={() => void create()}>
                  Create
                </Button>
                {target ? (
                  <>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={isBusy}
                      onClick={() => void removeVersion()}
                    >
                      Delete v{target.version}
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={isBusy}
                      onClick={() => void removeQuestionnaire()}
                    >
                      Delete {target.questionnaire}
                    </Button>
                  </>
                ) : null}
              </HStack>
              <Text size="sm" color="muted-foreground">
                Deleting is refused once a version has been answered — fork it instead, which the
                editor&rsquo;s own bar does.
              </Text>
            </VStack>
          </CardContent>
        </Card>

        {target ? (
          <QuestionnaireEditor
            key={`${target.questionnaire}-${target.version}`}
            api={editorApi}
            questionnaire={target.questionnaire}
            version={target.version}
            onForked={(draft) => {
              void refresh({
                questionnaire: draft.questionnaire.key,
                version: draft.version,
              })
            }}
            onSaved={() => {
              void refresh()
            }}
          />
        ) : null}
      </VStack>
    </Container>
  )
}

function describe(cause: unknown): string {
  return cause instanceof Error ? cause.message : String(cause)
}
