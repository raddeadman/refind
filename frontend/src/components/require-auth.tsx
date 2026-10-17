import { Loader2Icon } from 'lucide-react'
import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router'

import type { Role } from '@/api/generated/model'
import { useAuth } from '@/lib/auth-context'

/**
 * Wrap a route element to require a login (and optionally a role):
 *   <RequireAuth roles={['officer', 'admin']}><ReviewQueue /></RequireAuth>
 * The API enforces the same rules; this only gives a nicer experience.
 */
export function RequireAuth({ children, roles }: { children: ReactNode; roles?: Role[] }) {
  const { user, isLoading } = useAuth()
  const location = useLocation()

  if (isLoading) return <Loader2Icon className="mx-auto mt-24 size-8 animate-spin text-muted-foreground" />
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />
  if (roles && !roles.includes(user.role)) {
    return <p className="py-24 text-center text-muted-foreground">You do not have access to this page.</p>
  }
  return children
}
