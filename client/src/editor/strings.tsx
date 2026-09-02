/**
 * How the catalogue reaches a component.
 *
 * Every part of the editor is exported on its own, so a project can compose an
 * interface out of `Outline` and the forms without `QuestionnaireEditor` around
 * them.  That rules out passing the strings down as props from the top: there
 * is no top.  So the catalogue rides a context, and each component also takes
 * its own `strings` prop, which wins over the context for that subtree.
 *
 * React is the only thing this needs, and it is already a peer dependency.
 */

import { createContext, useContext, useMemo, type ReactNode } from "react"

import {
  defaultStrings,
  resolveStrings,
  translator,
  type QuestionnaireStrings,
  type StringOverrides,
  type Translate,
} from "../strings.js"

const StringsContext = createContext<QuestionnaireStrings>(defaultStrings)

export interface QuestionnaireStringsProviderProps {
  /** Whatever is left out stays English. */
  strings?: StringOverrides
  children: ReactNode
}

/** Translate everything rendered inside. */
export function QuestionnaireStringsProvider({
  strings,
  children,
}: QuestionnaireStringsProviderProps) {
  const value = useMemo(() => resolveStrings(strings), [strings])
  return <StringsContext.Provider value={value}>{children}</StringsContext.Provider>
}

/**
 * The catalogue in force here, with *overrides* -- a component's own `strings`
 * prop -- laid over it.
 *
 * Note the memo key: `overrides` is usually an object literal written inline in
 * JSX, so it is a new object on every render and cannot be depended on
 * directly. Its entries can, and there are few enough of them for that to be
 * cheaper than the re-renders it saves.
 */
export function useStringCatalog(overrides?: StringOverrides): QuestionnaireStrings {
  const inherited = useContext(StringsContext)
  const identity = overrides ? JSON.stringify(overrides) : ""
  return useMemo(
    () => (overrides ? { ...inherited, ...overrides } : inherited),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [inherited, identity],
  )
}

/** `useStringCatalog`, as the lookup function components actually call. */
export function useStrings(overrides?: StringOverrides): Translate {
  const catalog = useStringCatalog(overrides)
  return useMemo(() => translator(catalog), [catalog])
}

/** What every component that renders copy accepts. */
export interface WithStrings {
  /** Overrides for this subtree, laid over whatever the context provides. */
  strings?: StringOverrides
}
