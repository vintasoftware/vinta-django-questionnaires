/**
 * Who is signed in, for the pages that need someone to be.
 *
 * The session is Django's own, so the credentials are the admin's credentials
 * and the cookie is the same cookie. All this holds is what the server said
 * about it, fetched once and refreshed when it changes.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react"

const SESSION = "/demo-api/auth/session/"

export interface Identity {
  isAuthenticated: boolean
  isStaff: boolean
  username: string
}

const ANONYMOUS: Identity = { isAuthenticated: false, isStaff: false, username: "" }

export interface Session {
  identity: Identity
  isLoading: boolean
  signIn: (username: string, password: string) => Promise<string | null>
  signOut: () => Promise<void>
}

const SessionContext = createContext<Session | null>(null)

function csrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]*)/)
  return match?.[1] ? decodeURIComponent(match[1]) : ""
}

async function call(init: RequestInit = {}): Promise<Response> {
  return fetch(SESSION, {
    credentials: "same-origin",
    ...init,
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      "X-CSRFToken": csrfToken(),
      ...(init.headers ?? {}),
    },
  })
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [identity, setIdentity] = useState<Identity>(ANONYMOUS)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    // The same call sets the CSRF cookie, which every write below needs.
    call()
      .then((response) => (response.ok ? response.json() : ANONYMOUS))
      .then(setIdentity)
      .catch(() => setIdentity(ANONYMOUS))
      .finally(() => setIsLoading(false))
  }, [])

  const signIn = useCallback(async (username: string, password: string) => {
    const response = await call({
      method: "POST",
      body: JSON.stringify({ username, password }),
    })
    const payload = (await response.json().catch(() => ({}))) as Partial<Identity> & {
      detail?: string
    }
    if (!response.ok) {
      return payload.detail ?? "That did not work."
    }
    setIdentity({ ...ANONYMOUS, ...payload })
    return null
  }, [])

  const signOut = useCallback(async () => {
    await call({ method: "DELETE" })
    setIdentity(ANONYMOUS)
  }, [])

  const value = useMemo(
    () => ({ identity, isLoading, signIn, signOut }),
    [identity, isLoading, signIn, signOut],
  )
  return <SessionContext value={value}>{children}</SessionContext>
}

export function useSession(): Session {
  const session = useContext(SessionContext)
  if (!session) throw new Error("useSession needs a SessionProvider above it.")
  return session
}
