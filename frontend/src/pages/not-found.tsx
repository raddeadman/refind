import { Link } from 'react-router'

import { Button } from '@/components/ui/button'

export function NotFoundPage() {
  return (
    <div className="py-24 text-center">
      <h1 className="text-2xl font-semibold">Page not found</h1>
      <Button asChild variant="link">
        <Link to="/">Back to home</Link>
      </Button>
    </div>
  )
}
