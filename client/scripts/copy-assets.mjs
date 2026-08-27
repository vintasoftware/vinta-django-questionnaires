/** Copy the stylesheet next to the compiled editor, since tsc only emits JS. */
import { copyFileSync, mkdirSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const here = dirname(fileURLToPath(import.meta.url))
const dist = join(here, "..", "dist")
mkdirSync(dist, { recursive: true })
copyFileSync(join(here, "..", "src", "editor.css"), join(dist, "editor.css"))
