import { useProviders } from '@/api/generated/auth/auth'
import { GoogleIcon } from '@/components/google-icon'
import { Button } from '@/components/ui/button'
import { FieldSeparator } from '@/components/ui/field'

/** "Continue with Google" – hidden until the API has Google credentials. */
export function GoogleButton() {
  const { data } = useProviders({ query: { staleTime: Infinity } })
  if (!data?.data.google) return null

  return (
    <>
      <Button variant="outline" className="w-full" asChild>
        {/* A full page navigation: the API redirects to Google and back. */}
        <a href="/api/auth/google/login">
          <GoogleIcon className="size-4" />
          Continue with Google
        </a>
      </Button>
      <FieldSeparator>or</FieldSeparator>
    </>
  )
}
