import { Loader2Icon } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router'

import { errorMessage } from '@/api/fetcher'
import { useLogin } from '@/api/generated/auth/auth'
import { AuthCard } from '@/components/auth-card'
import { GoogleButton } from '@/components/google-button'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Field, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { useAuth } from '@/lib/auth-context'

export function LoginPage() {
  const { signIn } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [searchParams] = useSearchParams()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const login = useLogin()

  // Where to go after logging in (set by pages that require a login).
  const from = (location.state as { from?: string } | null)?.from ?? '/'
  const googleError = searchParams.get('error')

  function onSubmit(event: FormEvent) {
    event.preventDefault()
    login.mutate(
      { data: { username: email, password } },
      {
        onSuccess: (response) => {
          signIn(response.data.access_token)
          navigate(from, { replace: true })
        },
      },
    )
  }

  return (
    <AuthCard title="Welcome back" description="Log in with your university account">
      <form onSubmit={onSubmit}>
        <FieldGroup>
          {(login.error || googleError) && (
            <Alert variant="destructive">
              <AlertDescription>{login.error ? errorMessage(login.error) : googleError}</AlertDescription>
            </Alert>
          )}
          <GoogleButton />
          <Field>
            <FieldLabel htmlFor="email">University email</FieldLabel>
            <Input
              id="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </Field>
          <Field>
            <FieldLabel htmlFor="password">Password</FieldLabel>
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </Field>
          <Button type="submit" className="w-full" disabled={login.isPending}>
            {login.isPending && <Loader2Icon className="animate-spin" />}
            Log in
          </Button>
          <p className="text-center text-sm text-muted-foreground">
            No account yet?{' '}
            <Link to="/register" className="text-foreground underline underline-offset-4">
              Create one
            </Link>
          </p>
        </FieldGroup>
      </form>
    </AuthCard>
  )
}
