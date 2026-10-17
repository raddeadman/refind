import { CircleCheckIcon, CircleXIcon, Loader2Icon } from 'lucide-react'
import { useEffect, useRef } from 'react'
import { Link, useSearchParams } from 'react-router'

import { errorMessage } from '@/api/fetcher'
import { useVerifyEmail } from '@/api/generated/auth/auth'
import { AuthCard } from '@/components/auth-card'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/lib/auth-context'

/** Opened from the link in the verification email: /verify-email?token=... */
export function VerifyEmailPage() {
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token')
  const { user, refresh } = useAuth()
  const verify = useVerifyEmail()
  const sent = useRef(false)

  useEffect(() => {
    // The token is one-time: guard against StrictMode running effects twice.
    if (!token || sent.current) return
    sent.current = true
    verify.mutate({ data: { token } }, { onSuccess: refresh })
  }, [token, verify, refresh])

  if (!token || verify.isError) {
    return (
      <AuthCard title="Link not valid">
        <div className="flex flex-col items-center gap-4 text-center text-sm text-muted-foreground">
          <CircleXIcon className="size-10 text-destructive" />
          <p>{token ? errorMessage(verify.error) : 'This page needs the link from your verification email.'}</p>
          <p>Log in to ask for a new link.</p>
          <Button asChild className="w-full">
            <Link to="/login">Log in</Link>
          </Button>
        </div>
      </AuthCard>
    )
  }

  if (verify.isSuccess) {
    return (
      <AuthCard title="Email verified">
        <div className="flex flex-col items-center gap-4 text-center text-sm text-muted-foreground">
          <CircleCheckIcon className="size-10 text-green-600" />
          <p>Your account is active. You can now report items and submit claims.</p>
          <Button asChild className="w-full">
            <Link to={user ? '/' : '/login'}>{user ? 'Continue' : 'Log in'}</Link>
          </Button>
        </div>
      </AuthCard>
    )
  }

  return (
    <AuthCard title="Verifying your email…">
      <Loader2Icon className="mx-auto size-8 animate-spin text-muted-foreground" />
    </AuthCard>
  )
}
