import { createFileRoute } from "@tanstack/react-router"

import { ResponsesTable } from "../components/ResponsesTable"
import { StaffOnly } from "../components/SignIn"

export const Route = createFileRoute("/responses")({
  component: () => (
    <StaffOnly>
      <ResponsesTable />
    </StaffOnly>
  ),
})
