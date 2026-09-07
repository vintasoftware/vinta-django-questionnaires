/** Copy the stylesheets next to the compiled output, since tsc only emits JS. */
import { copyFileSync, mkdirSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const here = dirname(fileURLToPath(import.meta.url))
const dist = join(here, "..", "dist")
mkdirSync(dist, { recursive: true })
for (const sheet of ["editor.css", "widgets.css"]) {
  copyFileSync(join(here, "..", "src", sheet), join(dist, sheet))
}
