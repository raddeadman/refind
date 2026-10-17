import { Loader2Icon } from 'lucide-react'
import { useEffect } from 'react'
import { useNavigate } from 'react-router'

import { useAuth } from '@/lib/auth-context'

/** The API redirects here after Google sign-in: /auth/callback#token=... */
export function AuthCallbackPage() {
  const { signIn } = useAuth()
  const navigate = useNavigate()

  useEffect(() => {
    const token = new URLSearchParams(window.location.hash.slice(1)).get('token')
    if (token) signIn(token)
    // replace: the token never stays in the address bar or history.
    navigate(token ? '/' : '/login?error=Google+sign-in+failed', { replace: true })
  }, [signIn, navigate])

  return <Loader2Icon className="mx-auto mt-24 size-8 animate-spin text-muted-foreground" />
}
