import { Loader2Icon, MailCheckIcon } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'

import { errorMessage } from '@/api/fetcher'
import { useRegister, useResendVerification } from '@/api/generated/auth/auth'
import { AuthCard } from '@/components/auth-card'
import { GoogleButton } from '@/components/google-button'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'

export function RegisterPage() {
  const [form, setForm] = useState({ name: '', email: '', studentId: '', password: '', confirm: '' })
  const register = useRegister()
  const resend = useResendVerification()

  const mismatch = form.confirm !== '' && form.password !== form.confirm
  const set = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [key]: e.target.value }))

  function onSubmit(event: FormEvent) {
    event.preventDefault()
    if (mismatch) return
    register.mutate({
      data: { name: form.name, email: form.email, password: form.password, studentId: form.studentId || null },
    })
  }

  if (register.isSuccess) {
    return (
      <AuthCard title="Check your inbox" description={<>We sent a verification link to <b>{form.email}</b>.</>}>
        <div className="flex flex-col items-center gap-4 text-center text-sm text-muted-foreground">
          <MailCheckIcon className="size-10" />
          <p>The link is valid for 24 hours. You can log in now, but you need to verify before reporting items or claiming.</p>
          <Button
            variant="outline"
            className="w-full"
            disabled={resend.isPending}
            onClick={() =>
              resend.mutate({ data: { email: form.email } }, { onSuccess: () => toast.success('Link sent again') })
            }
          >
            Resend link
          </Button>
          <Button asChild className="w-full">
            <Link to="/login">Go to log in</Link>
          </Button>
        </div>
      </AuthCard>
    )
  }

  return (
    <AuthCard title="Create your account" description="Only university email addresses can sign up">
      <form onSubmit={onSubmit}>
        <FieldGroup>
          {register.error && (
            <Alert variant="destructive">
              <AlertDescription>{errorMessage(register.error)}</AlertDescription>
            </Alert>
          )}
          <GoogleButton />
          <Field>
            <FieldLabel htmlFor="name">Full name</FieldLabel>
            <Input id="name" autoComplete="name" required maxLength={100} value={form.name} onChange={set('name')} />
          </Field>
          <Field>
            <FieldLabel htmlFor="email">University email</FieldLabel>
            <Input id="email" type="email" autoComplete="email" required value={form.email} onChange={set('email')} />
          </Field>
          <Field>
            <FieldLabel htmlFor="studentId">Student / staff ID</FieldLabel>
            <Input id="studentId" maxLength={20} value={form.studentId} onChange={set('studentId')} />
            <FieldDescription>Checked against your ID card at handover.</FieldDescription>
          </Field>
          <Field>
            <FieldLabel htmlFor="password">Password</FieldLabel>
            <Input
              id="password"
              type="password"
              autoComplete="new-password"
              required
              minLength={8}
              maxLength={72}
              value={form.password}
              onChange={set('password')}
            />
            <FieldDescription>At least 8 characters.</FieldDescription>
          </Field>
          <Field data-invalid={mismatch || undefined}>
            <FieldLabel htmlFor="confirm">Confirm password</FieldLabel>
            <Input
              id="confirm"
              type="password"
              autoComplete="new-password"
              required
              aria-invalid={mismatch || undefined}
              value={form.confirm}
              onChange={set('confirm')}
            />
            {mismatch && <FieldError>Passwords do not match</FieldError>}
          </Field>
          <Button type="submit" className="w-full" disabled={register.isPending}>
            {register.isPending && <Loader2Icon className="animate-spin" />}
            Create account
          </Button>
          <p className="text-center text-sm text-muted-foreground">
            Already registered?{' '}
            <Link to="/login" className="text-foreground underline underline-offset-4">
              Log in
            </Link>
          </p>
        </FieldGroup>
      </form>
    </AuthCard>
  )
}
