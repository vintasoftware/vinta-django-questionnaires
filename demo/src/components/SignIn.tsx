/**
 * The sign-in page, and the gate the back-office pages sit behind.
 *
 * There is nothing questionnaire-specific here: it is Django's own session,
 * signed into with the same credentials as the admin, which is the point --
 * authoring is a staff job and the project already knows who its staff are.
 */

import { useState, type ReactNode } from "react"

import { Link } from "@tanstack/react-router"
import { Alert, AlertDescription, AlertTitle } from "vinta-schedule-design-system/ui/alert"
import { Button } from "vinta-schedule-design-system/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "vinta-schedule-design-system/ui/card"
import { Input } from "vinta-schedule-design-system/ui/input"
import { Label } from "vinta-schedule-design-system/ui/label"
import { Spinner } from "vinta-schedule-design-system/ui/spinner"
import { Container, HStack, Text, VStack } from "vinta-schedule-design-system/layout"

import { useSession } from "../auth"

export function SignIn({ onSignedIn }: { onSignedIn?: () => void }) {
  const { identity, signIn, signOut } = useSession()
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [failure, setFailure] = useState<string | null>(null)
  const [isBusy, setIsBusy] = useState(false)

  if (identity.isAuthenticated) {
    return (
      <Container width="prose" py={10}>
        <Card>
          <CardHeader>
            <CardTitle>Signed in as {identity.username}</CardTitle>
          </CardHeader>
          <CardContent>
            <VStack gap={4}>
              <Text color="muted-foreground">
                {identity.isStaff
                  ? "This account can author questionnaires and read responses."
                  : "This account is not staff, so the back office will refuse it."}
              </Text>
              <HStack gap={2}>
                <Button asChild>
                  <Link to="/editor">Go to the editor</Link>
                </Button>
                <Button variant="outline" asChild>
                  <Link to="/responses">Responses</Link>
                </Button>
                <Button variant="ghost" onClick={() => void signOut()}>
                  Sign out
                </Button>
              </HStack>
            </VStack>
          </CardContent>
        </Card>
      </Container>
    )
  }

  return (
    <Container width="prose" py={10}>
      <Card>
        <CardHeader>
          <CardTitle>Sign in</CardTitle>
        </CardHeader>
        <CardContent>
          <form
            onSubmit={(event) => {
              event.preventDefault()
              setIsBusy(true)
              setFailure(null)
              void signIn(username, password)
                .then((error) => {
                  setFailure(error)
                  if (!error) onSignedIn?.()
                })
                .finally(() => setIsBusy(false))
            }}
          >
            <VStack gap={4}>
              <Text color="muted-foreground">
                Your Django admin credentials. The seeded example project makes{" "}
                <Text as="code">demo</Text> / <Text as="code">demo</Text>.
              </Text>

              {failure ? (
                <Alert variant="destructive">
                  <AlertTitle>Not signed in</AlertTitle>
                  <AlertDescription>{failure}</AlertDescription>
                </Alert>
              ) : null}

              <VStack gap={2}>
                <Label htmlFor="username">Username</Label>
                <Input
                  id="username"
                  autoComplete="username"
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                />
              </VStack>
              <VStack gap={2}>
                <Label htmlFor="password">Password</Label>
                <Input
                  id="password"
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                />
              </VStack>

              <HStack gap={2}>
                <Button type="submit" disabled={isBusy || !username || !password}>
                  {isBusy ? "Signing in…" : "Sign in"}
                </Button>
                <Button variant="ghost" asChild>
                  <Link to="/">Back to the form</Link>
                </Button>
              </HStack>
            </VStack>
          </form>
        </CardContent>
      </Card>
    </Container>
  )
}

/** Renders *children* only for a signed-in staff user. */
export function StaffOnly({ children }: { children: ReactNode }) {
  const { identity, isLoading } = useSession()

  if (isLoading) {
    return (
      <Container width="prose" py={10}>
        <HStack gap={3} align="center">
          <Spinner />
          <Text color="muted-foreground">Checking who you are…</Text>
        </HStack>
      </Container>
    )
  }
  if (!identity.isAuthenticated) return <SignIn />
  if (!identity.isStaff) {
    return (
      <Container width="prose" py={10}>
        <Alert variant="destructive">
          <AlertTitle>Not allowed</AlertTitle>
          <AlertDescription>
            {identity.username} is signed in but is not staff, and the authoring API is staff
            only. That rule is the package's own default, not something the demo adds.
          </AlertDescription>
        </Alert>
      </Container>
    )
  }
  return <>{children}</>
}
