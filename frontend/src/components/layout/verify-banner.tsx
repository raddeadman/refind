import { toast } from 'sonner'

import { useResendVerification } from '@/api/generated/auth/auth'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/lib/auth-context'

/** Shown to logged-in users who have not verified their email yet. */
export function VerifyBanner() {
  const { user } = useAuth()
  const resend = useResendVerification()
  if (user?.status !== 'unverified') return null

  return (
    <div className="border-b bg-amber-50 text-amber-900 dark:bg-amber-950 dark:text-amber-100">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-4 gap-y-1 px-4 py-2 text-sm">
        <span>Verify your email ({user.email}) to report items and submit claims.</span>
        <Button
          size="sm"
          variant="link"
          className="h-auto p-0 text-inherit underline"
          disabled={resend.isPending || resend.isSuccess}
          onClick={() =>
            resend.mutate({ data: { email: user.email } }, { onSuccess: () => toast.success('Verification link sent') })
          }
        >
          {resend.isSuccess ? 'Link sent' : 'Resend link'}
        </Button>
      </div>
    </div>
  )
}
