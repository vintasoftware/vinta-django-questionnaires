import { createFileRoute } from "@tanstack/react-router"

import { Questionnaire } from "../components/Questionnaire"

export const Route = createFileRoute("/")({
  component: Questionnaire,
})
