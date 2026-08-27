/// <reference types="vite/client" />
import { HeadContent, Outlet, Scripts, createRootRoute } from "@tanstack/react-router"

import { SessionProvider } from "../auth"

import designSystem from "vinta-schedule-design-system/styles.css?url"
import editorStyles from "@vintasoftware/django-questionnaires/editor.css?url"
import overrides from "../styles.css?url"

export const Route = createRootRoute({
  head: () => ({
    meta: [
      { charSet: "utf-8" },
      { name: "viewport", content: "width=device-width, initial-scale=1" },
      { title: "Questionnaires demo" },
    ],
    links: [
      { rel: "stylesheet", href: designSystem },
      { rel: "stylesheet", href: editorStyles },
      { rel: "stylesheet", href: overrides },
    ],
  }),
  component: RootDocument,
})

function RootDocument() {
  return (
    <html lang="en">
      <head>
        <HeadContent />
      </head>
      <body>
        <SessionProvider>
          <Outlet />
        </SessionProvider>
        <Scripts />
      </body>
    </html>
  )
}
