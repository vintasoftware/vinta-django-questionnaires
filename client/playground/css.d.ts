/**
 * CSS is a side-effect import that Vite understands and tsc does not.
 *
 * Only the playground imports a stylesheet -- the package itself ships its CSS
 * for a host to import, and never reaches for one from TypeScript -- so the
 * declaration lives here rather than in `src`.
 */
declare module "*.css"
