import viteReact from "@vitejs/plugin-react"
import { tanstackStart } from "@tanstack/react-start/plugin/vite"
import { defineConfig } from "vite"

export default defineConfig({
  plugins: [tanstackStart(), viteReact()],
  server: {
    // Its own port, and strict: a demo that quietly moved would talk to a
    // Django that is not expecting it, and CSRF would fail confusingly.
    port: 5273,
    strictPort: true,
    // The Django example project. Going through the proxy keeps the browser on
    // one origin, so the session and CSRF cookies behave the way they would in
    // production behind a single domain.
    proxy: {
      "/demo-api": { target: "http://localhost:8000", changeOrigin: false },
    },
  },
  ssr: {
    // The design system ships TypeScript sources rather than a build, so Vite
    // has to compile it on the server side too.
    noExternal: ["vinta-schedule-design-system"],
  },
  resolve: {
    // The design system and the app must share one React instance. Without
    // this, the source-shipped design system pulls in its own and every hook
    // it calls throws.
    dedupe: ["react", "react-dom"],
  },
})
