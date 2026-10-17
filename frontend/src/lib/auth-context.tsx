import { useQueryClient } from '@tanstack/react-query'
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

import { ApiError } from '@/api/fetcher'
import { getMeQueryKey, useMe } from '@/api/generated/auth/auth'
import type { UserOut } from '@/api/generated/model'
import { getToken, setToken } from '@/lib/auth'

type AuthState = {
  /** The logged-in user, or null for a guest. */
  user: UserOut | null
  /** True while a stored token is being checked on page load. */
  isLoading: boolean
  signIn: (token: string) => void
  signOut: () => void
  /** Reload the user (e.g. after verifying the email). */
  refresh: () => void
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [token, setTokenState] = useState(getToken)
  const me = useMe({ query: { enabled: token !== null, retry: false, staleTime: 60_000 } })

  const signOut = useCallback(() => {
    setToken(null)
    setTokenState(null)
    queryClient.clear()
  }, [queryClient])

  const signIn = useCallback(
    (newToken: string) => {
      setToken(newToken)
      setTokenState(newToken)
      queryClient.invalidateQueries({ queryKey: getMeQueryKey() })
    },
    [queryClient],
  )

  // Expired token, or the account was disabled: back to guest.
  useEffect(() => {
    if (me.error instanceof ApiError && me.error.status === 401) signOut()
  }, [me.error, signOut])

  const value = useMemo<AuthState>(
    () => ({
      user: token ? (me.data?.data ?? null) : null,
      isLoading: token !== null && me.isPending,
      signIn,
      signOut,
      refresh: () => queryClient.invalidateQueries({ queryKey: getMeQueryKey() }),
    }),
    [token, me.data, me.isPending, signIn, signOut, queryClient],
  )

  return <AuthContext value={value}>{children}</AuthContext>
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside <AuthProvider>')
  return context
}
