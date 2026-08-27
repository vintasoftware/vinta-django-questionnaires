import type { Diagnostic } from "@vintasoftware/django-questionnaires"
import { Badge } from "vinta-schedule-design-system/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "vinta-schedule-design-system/ui/card"
import { Text, VStack } from "vinta-schedule-design-system/layout"

/**
 * What the client could not check, and why.
 *
 * In a real app this is where `onDiagnostic` would hand things to Sentry. It
 * is on screen here because it is the point: a rule the browser cannot run is
 * visible rather than silently missing.
 */
export function DiagnosticsPanel({ diagnostics }: { diagnostics: Diagnostic[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Client diagnostics</CardTitle>
      </CardHeader>
      <CardContent>
        <VStack gap={3}>
          {diagnostics.length === 0 ? (
            <Text size="sm" color="muted-foreground">
              Nothing so far. Every rule on this page runs in the browser.
            </Text>
          ) : (
            diagnostics.map((diagnostic, index) => (
              <VStack key={`${diagnostic.code}-${index}`} gap={1}>
                <Badge variant={diagnostic.code === "server-only" ? "outline" : "secondary"}>
                  {diagnostic.code}
                </Badge>
                <Text size="sm" color="muted-foreground">
                  {diagnostic.message}
                </Text>
              </VStack>
            ))
          )}
        </VStack>
      </CardContent>
    </Card>
  )
}
