import { createFileRoute } from "@tanstack/react-router"

import { SignIn } from "../components/SignIn"

export const Route = createFileRoute("/login")({
  component: SignIn,
})
