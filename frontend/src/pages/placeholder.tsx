import { ConstructionIcon } from 'lucide-react'

import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

type Props = { title: string; owner: string; milestone: string }

export function PlaceholderPage({ title, owner, milestone }: Props) {
  return (
    <Card className="mx-auto max-w-lg">
      <CardHeader>
        <ConstructionIcon className="size-6 text-muted-foreground" />
        <CardTitle>{title}</CardTitle>
        <CardDescription>
          Not built yet – owner: {owner}, due {milestone}.
        </CardDescription>
      </CardHeader>
    </Card>
  )
}
