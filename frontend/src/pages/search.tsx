/**
 * Search found items (proposal §6.1, owner: Faisal, M3).
 *
 * Filters live in the URL (?q=&category=&building=...) so a search can be
 * shared or bookmarked. What each card shows depends on the view the API
 * returns: guests get the public fields, logged-in users also see colour
 * and brand, and reporters/officers see everything.
 */
import { MapPinIcon, SearchIcon, XIcon } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router'

import { errorMessage } from '@/api/fetcher'
import { useListCategories } from '@/api/generated/categories/categories'
import { useListItems } from '@/api/generated/items/items'
import {
  LocationBuilding,
  type ItemFull,
  type ItemMember,
  type ItemPublic,
  type ItemStatus,
  type ListItemsBuilding,
  type ListItemsParams,
} from '@/api/generated/model'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { useAuth } from '@/lib/auth-context'

const PAGE_SIZE = 12
const ALL = 'all' // Radix Select does not allow an empty value
const BUILDINGS = Object.values(LocationBuilding)

type Item = ItemPublic | ItemMember | ItemFull

const STATUS_LABEL: Record<ItemStatus, string> = {
  open: 'Open',
  matched: 'Possible match',
  claimed: 'Claimed',
  returned: 'Returned',
  archived: 'Archived',
}

function formatDate(iso: string) {
  // Stored as midnight UTC: format in UTC so the day does not shift.
  return new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' })
}

export function SearchPage() {
  const { user } = useAuth()
  const [params, setParams] = useSearchParams()
  const [text, setText] = useState(params.get('q') ?? '')
  const categories = useListCategories()

  const page = Math.max(1, Number(params.get('page')) || 1)
  const query: ListItemsParams = {
    type: 'found',
    q: params.get('q') || undefined,
    category: params.get('category') || undefined,
    building: (params.get('building') as ListItemsBuilding | null) || undefined,
    dateFrom: params.get('dateFrom') || undefined,
    dateTo: params.get('dateTo') || undefined,
    page,
    pageSize: PAGE_SIZE,
  }
  const { data, isPending, error } = useListItems(query, { query: { placeholderData: (previous) => previous } })
  const result = data?.data
  const pages = result ? Math.max(1, Math.ceil(result.total / PAGE_SIZE)) : 1
  const categoryName = (code: string) => categories.data?.data.find((c) => c.code === code)?.name ?? code

  /** Change one filter and go back to page 1. */
  function update(key: string, value: string | null) {
    setParams((p) => {
      const next = new URLSearchParams(p)
      if (value && value !== ALL) next.set(key, value)
      else next.delete(key)
      if (key !== 'page') next.delete('page')
      return next
    })
  }

  function onSearch(event: FormEvent) {
    event.preventDefault()
    update('q', text.trim() || null)
  }

  const filtered = ['q', 'category', 'building', 'dateFrom', 'dateTo'].some((k) => params.get(k))

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Search found items</h1>
        <p className="text-muted-foreground">
          {user
            ? 'Found something that looks like yours? Open it to start a claim.'
            : 'Log in to see colour and brand, and to claim an item.'}
        </p>
      </div>

      <div className="space-y-3">
        <form onSubmit={onSearch} className="flex gap-2">
          <Input
            aria-label="Keywords"
            placeholder="Keywords, e.g. wallet, Apple, blue"
            maxLength={100}
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <Button type="submit">
            <SearchIcon /> Search
          </Button>
        </form>

        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-[1fr_1fr_auto_auto_auto]">
          <Select value={params.get('category') ?? ALL} onValueChange={(v) => update('category', v)}>
            <SelectTrigger aria-label="Category" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>All categories</SelectItem>
              {categories.data?.data.map((c) => (
                <SelectItem key={c.code} value={c.code}>
                  {c.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={params.get('building') ?? ALL} onValueChange={(v) => update('building', v)}>
            <SelectTrigger aria-label="Building" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>All buildings</SelectItem>
              {BUILDINGS.map((b) => (
                <SelectItem key={b} value={b}>
                  {b}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Input
            type="date"
            aria-label="Found from"
            title="Found from"
            value={params.get('dateFrom') ?? ''}
            onChange={(e) => update('dateFrom', e.target.value)}
          />
          <Input
            type="date"
            aria-label="Found until"
            title="Found until"
            value={params.get('dateTo') ?? ''}
            onChange={(e) => update('dateTo', e.target.value)}
          />
          <Button
            variant="ghost"
            disabled={!filtered}
            onClick={() => {
              setText('')
              setParams({})
            }}
          >
            <XIcon /> Clear
          </Button>
        </div>
      </div>

      {error ? (
        <Alert variant="destructive">
          <AlertTitle>Could not load items</AlertTitle>
          <AlertDescription>{errorMessage(error)}</AlertDescription>
        </Alert>
      ) : null}

      {result && (
        <p className="text-sm text-muted-foreground">
          {result.total} item{result.total === 1 ? '' : 's'}
        </p>
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {isPending && Array.from({ length: 6 }, (_, i) => <Skeleton key={i} className="h-40 rounded-xl" />)}
        {result?.items.map((item) => <ItemCard key={item.id} item={item} categoryName={categoryName} />)}
      </div>

      {result && result.total === 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Nothing found</CardTitle>
            <CardDescription>
              Try fewer filters, or{' '}
              <Link to="/report" className="text-foreground underline underline-offset-4">
                report your lost item
              </Link>{' '}
              and we will tell you when a match is handed in.
            </CardDescription>
          </CardHeader>
        </Card>
      )}

      {result && pages > 1 && (
        <div className="flex items-center justify-center gap-3">
          <Button variant="outline" disabled={page <= 1} onClick={() => update('page', String(page - 1))}>
            Previous
          </Button>
          <span className="text-sm text-muted-foreground">
            Page {page} of {pages}
          </span>
          <Button variant="outline" disabled={page >= pages} onClick={() => update('page', String(page + 1))}>
            Next
          </Button>
        </div>
      )}
    </div>
  )
}

function ItemCard({ item, categoryName }: { item: Item; categoryName: (code: string) => string }) {
  const full = item.access === 'full' ? item : null
  const attributes = item.access === 'public' ? null : item.attributes
  const traits = [attributes?.color, attributes?.brand].filter(Boolean)

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-start justify-between gap-2">
          <span>{item.title}</span>
          <Badge variant={item.status === 'open' ? 'secondary' : 'outline'}>{STATUS_LABEL[item.status]}</Badge>
        </CardTitle>
        <CardDescription className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <span>{categoryName(item.category)}</span>
          <span className="flex items-center gap-1">
            <MapPinIcon className="size-3.5" />
            {item.location.building}
          </span>
          <span>{formatDate(item.date)}</span>
        </CardDescription>
      </CardHeader>
      {(traits.length > 0 || full) && (
        <CardContent className="space-y-2 text-sm">
          {traits.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {traits.map((t) => (
                <Badge key={t} variant="outline" className="capitalize">
                  {t}
                </Badge>
              ))}
            </div>
          )}
          {full?.description && <p className="text-muted-foreground">{full.description}</p>}
          {full?.heldAt && <p className="text-muted-foreground">Held at: {full.heldAt}</p>}
        </CardContent>
      )}
    </Card>
  )
}
