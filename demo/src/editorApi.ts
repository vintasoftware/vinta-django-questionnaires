/**
 * The authoring API, as the demo uses it.
 *
 * The package ships the client; all this adds is where the demo's copy of the
 * authoring URLs lives and the CSRF header Django wants on a write. The
 * session cookie comes from signing in, which is what `auth.tsx` does.
 */

import { createEditorClient } from "vinta-django-questionnaires-client"

import { csrfToken } from "./api"

export const editorApi = createEditorClient({
  baseUrl: "/demo-api/authoring/",
  headers: () => ({ "X-CSRFToken": csrfToken() }),
})
