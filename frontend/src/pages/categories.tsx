/**
 * Worked example of a page backed by the API – copy this pattern:
 *   1. call an Orval-generated hook (never write fetch() by hand),
 *   2. handle loading / error / empty states,
 *   3. render with shadcn components.
 */
import { ApiError } from '@/api/fetcher'
import { useListCategories } from '@/api/generated/categories/categories'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'

export function CategoriesPage() {
  const { data, isPending, error } = useListCategories()

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Categories</h1>
        <p className="text-muted-foreground">Each category comes with default verification questions.</p>
      </div>

      {error ? (
        <Alert variant="destructive">
          <AlertTitle>Could not load categories</AlertTitle>
          <AlertDescription>{error instanceof ApiError ? error.message : 'Is the API running?'}</AlertDescription>
        </Alert>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {isPending &&
          Array.from({ length: 6 }, (_, i) => <Skeleton key={i} className="h-36 rounded-xl" />)}

        {data?.data.map((category) => (
          <Card key={category.code}>
            <CardHeader>
              <CardTitle className="flex items-center justify-between gap-2">
                {category.name}
                <Badge variant="secondary">{category.code}</Badge>
              </CardTitle>
              <CardDescription>{category.defaultQuestions?.length ?? 0} default questions</CardDescription>
            </CardHeader>
            <CardContent>
              <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
                {category.defaultQuestions?.map((q) => <li key={q}>{q}</li>)}
              </ul>
            </CardContent>
          </Card>
        ))}
      </div>

      {data && data.data.length === 0 && (
        <p className="text-muted-foreground">No categories yet. Run the seed script.</p>
      )}
    </div>
  )
}
