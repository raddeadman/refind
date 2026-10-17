import { Link } from 'react-router'

import { Button } from '@/components/ui/button'

export function HomePage() {
  return (
    <section className="mx-auto max-w-2xl py-16 text-center">
      <h1 className="text-4xl font-bold tracking-tight">Lost something on campus?</h1>
      <p className="mt-4 text-lg text-muted-foreground">
        Report lost and found items in one place. ReFind suggests likely matches automatically and checks ownership
        before anything is handed over.
      </p>
      <div className="mt-8 flex justify-center gap-3">
        <Button asChild size="lg">
          <Link to="/report">Report an item</Link>
        </Button>
        <Button asChild size="lg" variant="outline">
          <Link to="/search">Browse found items</Link>
        </Button>
      </div>
    </section>
  )
}
