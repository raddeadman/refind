import type { ReactNode } from 'react'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

/** Shared frame for the login / register / verify pages. */
export function AuthCard({ title, description, children }: { title: string; description?: ReactNode; children: ReactNode }) {
  return (
    <div className="mx-auto w-full max-w-sm py-8">
      <Card>
        <CardHeader className="text-center">
          <CardTitle className="text-xl">{title}</CardTitle>
          {description && <CardDescription>{description}</CardDescription>}
        </CardHeader>
        <CardContent>{children}</CardContent>
      </Card>
    </div>
  )
}
