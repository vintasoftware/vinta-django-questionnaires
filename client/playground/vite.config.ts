/**
 * The playground's dev server.
 *
 * Vite is already here as vitest's own dependency, so this costs the package no
 * new devDependency. There is no React plugin, which means a save reloads the
 * page rather than hot-swapping the component -- a fair trade for not adding a
 * dependency that only the playground would use.
 */

import { defineConfig } from "vite"

export default defineConfig({
  root: import.meta.dirname,
  server: { port: 5399, strictPort: true, open: false },
  // The package's own sources, not its build, so the playground shows what is
  // in the working tree rather than whatever was last compiled to `dist`.
  resolve: { dedupe: ["react", "react-dom"] },
})
