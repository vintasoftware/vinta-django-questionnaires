import type { QuestionnairePlan, ResponseProgress } from "vinta-django-questionnaires-client"
import { Badge } from "vinta-schedule-design-system/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "vinta-schedule-design-system/ui/card"
import { Progress } from "vinta-schedule-design-system/ui/progress"
import { HStack, Text, VStack } from "vinta-schedule-design-system/layout"

const REASONS: Record<string, string> = {
  manual_action: "Skipped for later",
  false_condition: "Not asked",
}

export function ProgressPanel({
  plan,
  progress,
}: {
  plan: QuestionnairePlan
  progress: ResponseProgress
}) {
  const skipped = new Map(progress.skipped.map((entry) => [entry.page, entry.reason]))
  const done = progress.completed.length
  const total = plan.pages.length

  return (
    <Card>
      <CardHeader>
        <CardTitle>Where you are</CardTitle>
      </CardHeader>
      <CardContent>
        <VStack gap={4}>
          <VStack gap={2}>
            <Progress value={total ? (done / total) * 100 : 0} />
            <Text size="sm" color="muted-foreground">
              {done} of {total} pages filled in
            </Text>
          </VStack>
          <VStack gap={2}>
            {plan.pages.map((page) => {
              const reason = skipped.get(page.key)
              const isCurrent = page.key === progress.current
              return (
                <HStack key={page.key} justify="between" align="center" gap={3}>
                  <Text weight={isCurrent ? "semibold" : "normal"}>{page.title ?? page.key}</Text>
                  {isCurrent ? (
                    <Badge>Here</Badge>
                  ) : progress.completed.includes(page.key) ? (
                    <Badge variant="secondary">Done</Badge>
                  ) : reason ? (
                    <Badge variant="outline">{REASONS[reason] ?? reason}</Badge>
                  ) : (
                    <Badge variant="outline">Pending</Badge>
                  )}
                </HStack>
              )
            })}
          </VStack>
        </VStack>
      </CardContent>
    </Card>
  )
}
