import { createFileRoute } from "@tanstack/react-router"

import { EditorScreen } from "../components/EditorScreen"
import { StaffOnly } from "../components/SignIn"

export const Route = createFileRoute("/editor")({
  component: () => (
    <StaffOnly>
      <EditorScreen />
    </StaffOnly>
  ),
})
