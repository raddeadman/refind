/**
 * Report a lost or found item (proposal §6.1, owner: Faisal, M3).
 *
 * Found items need at least one verification question; the answers are
 * hashed on the server and only used to check claims. Photos are uploaded
 * after the item is saved (POST /api/items/{id}/photos).
 */
import { CheckCircle2Icon, ImagePlusIcon, Loader2Icon, PlusIcon, Trash2Icon, XIcon } from 'lucide-react'
import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'

import { errorMessage } from '@/api/fetcher'
import { useListCategories } from '@/api/generated/categories/categories'
import { useCreateItem, useUploadItemPhotos } from '@/api/generated/items/items'
import { LocationBuilding, type ItemFull, type ItemType } from '@/api/generated/model'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Field, FieldDescription, FieldGroup, FieldLabel, FieldLegend, FieldSet } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { useAuth } from '@/lib/auth-context'
import { cn } from '@/lib/utils'

const MAX_PHOTOS = 4
const MAX_PHOTO_BYTES = 5 * 1024 * 1024
const MAX_QUESTIONS = 5
const BUILDINGS = Object.values(LocationBuilding)

type Question = { question: string; answer: string }

const today = () => new Date().toLocaleDateString('en-CA') // YYYY-MM-DD in local time

const emptyForm = () => ({
  title: '',
  category: '',
  color: '',
  brand: '',
  model: '',
  description: '',
  building: '',
  floor: '',
  area: '',
  details: '',
  date: today(),
  approxTime: '',
  heldAt: '',
  serialNumber: '',
})

/** Empty strings become null so optional fields are not sent as "". */
const opt = (value: string) => value.trim() || null

export function ReportPage() {
  const { user } = useAuth()
  const categories = useListCategories()
  const createItem = useCreateItem()
  const uploadPhotos = useUploadItemPhotos()

  const [type, setType] = useState<ItemType>('lost')
  const [form, setForm] = useState(emptyForm)
  const [questions, setQuestions] = useState<Question[]>([{ question: '', answer: '' }])
  const [photos, setPhotos] = useState<File[]>([])
  const [photoError, setPhotoError] = useState<string | null>(null)
  const [saved, setSaved] = useState<ItemFull | null>(null)

  const previews = useMemo(() => photos.map((file) => URL.createObjectURL(file)), [photos])
  useEffect(() => () => previews.forEach((url) => URL.revokeObjectURL(url)), [previews])

  const set = (key: keyof ReturnType<typeof emptyForm>) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setForm((f) => ({ ...f, [key]: e.target.value }))

  function chooseCategory(code: string) {
    setForm((f) => ({ ...f, category: code }))
    // Offer the category's default questions while the officer has not written any.
    const defaults = categories.data?.data.find((c) => c.code === code)?.defaultQuestions ?? []
    if (defaults.length && questions.every((q) => !q.question.trim() && !q.answer.trim())) {
      setQuestions(defaults.slice(0, MAX_QUESTIONS).map((question) => ({ question, answer: '' })))
    }
  }

  function setQuestion(index: number, key: keyof Question, value: string) {
    setQuestions((qs) => qs.map((q, i) => (i === index ? { ...q, [key]: value } : q)))
  }

  function addPhotos(files: FileList | null) {
    if (!files) return
    setPhotoError(null)
    const chosen = [...photos]
    for (const file of Array.from(files)) {
      if (!['image/jpeg', 'image/png'].includes(file.type)) {
        setPhotoError(`${file.name}: only JPEG and PNG photos are allowed`)
      } else if (file.size > MAX_PHOTO_BYTES) {
        setPhotoError(`${file.name} is larger than 5 MB`)
      } else if (chosen.length >= MAX_PHOTOS) {
        setPhotoError(`At most ${MAX_PHOTOS} photos per item`)
      } else {
        chosen.push(file)
      }
    }
    setPhotos(chosen)
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    const found = type === 'found'
    const item = await createItem
      .mutateAsync({
        data: {
          type,
          title: form.title.trim(),
          category: form.category,
          attributes: { color: opt(form.color), brand: opt(form.brand), model: opt(form.model) },
          description: opt(form.description),
          location: {
            building: form.building as LocationBuilding,
            floor: opt(form.floor),
            area: opt(form.area),
            details: opt(form.details),
          },
          date: form.date,
          approxTime: opt(form.approxTime),
          heldAt: found ? opt(form.heldAt) : null,
          verification: found
            ? questions.map((q) => ({ question: q.question.trim(), answer: q.answer.trim() }))
            : [],
          serialNumber: found ? opt(form.serialNumber) : null,
        },
      })
      .then((r) => r.data)
      .catch(() => null) // shown from createItem.error
    if (!item) return

    let result = item
    if (photos.length) {
      try {
        result = (await uploadPhotos.mutateAsync({ itemId: item.id, data: { files: photos } })).data
      } catch (error) {
        toast.error(`Report saved, but the photos were not: ${errorMessage(error)}`)
      }
    }
    setSaved(result)
  }

  function reset() {
    setForm(emptyForm())
    setQuestions([{ question: '', answer: '' }])
    setPhotos([])
    setSaved(null)
    createItem.reset()
    uploadPhotos.reset()
  }

  if (saved) {
    return (
      <Card className="mx-auto max-w-lg text-center">
        <CardHeader className="items-center">
          <CheckCircle2Icon className="mx-auto size-10 text-green-600" />
          <CardTitle>Report saved</CardTitle>
          <CardDescription>
            Your {saved.type} report “{saved.title}” is open
            {saved.photoIds.length ? ` with ${saved.photoIds.length} photo(s)` : ''}. We will notify you when a
            possible match turns up.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex justify-center gap-3">
          <Button variant="outline" onClick={reset}>
            Report another
          </Button>
          <Button asChild>
            <Link to="/search">Search found items</Link>
          </Button>
        </CardContent>
      </Card>
    )
  }

  if (user?.status !== 'active') {
    return (
      <Alert className="mx-auto max-w-lg">
        <AlertTitle>Verify your email first</AlertTitle>
        <AlertDescription>Open the link we emailed you, then come back to report an item.</AlertDescription>
      </Alert>
    )
  }

  const found = type === 'found'
  const busy = createItem.isPending || uploadPhotos.isPending

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Report an item</h1>
        <p className="text-muted-foreground">The more detail you give, the better the automatic matching works.</p>
      </div>

      <form onSubmit={onSubmit}>
        <FieldGroup>
          {createItem.error && (
            <Alert variant="destructive">
              <AlertDescription>{errorMessage(createItem.error)}</AlertDescription>
            </Alert>
          )}

          <div className="grid grid-cols-2 gap-2" role="radiogroup" aria-label="Report type">
            {(['lost', 'found'] as const).map((t) => (
              <Button
                key={t}
                type="button"
                role="radio"
                aria-checked={type === t}
                variant={type === t ? 'default' : 'outline'}
                onClick={() => setType(t)}
              >
                {t === 'lost' ? 'I lost something' : 'I found something'}
              </Button>
            ))}
          </div>

          <FieldSet>
            <FieldLegend>What is it?</FieldLegend>
            <FieldGroup>
              <Field>
                <FieldLabel htmlFor="title">Title</FieldLabel>
                <Input
                  id="title"
                  required
                  maxLength={100}
                  placeholder={found ? 'e.g. Wallet' : 'e.g. Black leather wallet'}
                  value={form.title}
                  onChange={set('title')}
                />
                {found && <FieldDescription>Keep it generic – guests can see the title.</FieldDescription>}
              </Field>
              <Field>
                <FieldLabel htmlFor="category">Category</FieldLabel>
                <Select required value={form.category} onValueChange={chooseCategory}>
                  <SelectTrigger id="category" className="w-full">
                    <SelectValue placeholder={categories.isPending ? 'Loading…' : 'Choose a category'} />
                  </SelectTrigger>
                  <SelectContent>
                    {categories.data?.data.map((c) => (
                      <SelectItem key={c.code} value={c.code}>
                        {c.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
              <div className="grid gap-4 sm:grid-cols-3">
                <Field>
                  <FieldLabel htmlFor="color">Colour</FieldLabel>
                  <Input id="color" maxLength={30} value={form.color} onChange={set('color')} />
                </Field>
                <Field>
                  <FieldLabel htmlFor="brand">Brand</FieldLabel>
                  <Input id="brand" maxLength={50} value={form.brand} onChange={set('brand')} />
                </Field>
                <Field>
                  <FieldLabel htmlFor="model">Model</FieldLabel>
                  <Input id="model" maxLength={50} value={form.model} onChange={set('model')} />
                </Field>
              </div>
              <Field>
                <FieldLabel htmlFor="description">Description</FieldLabel>
                <Textarea id="description" maxLength={1000} rows={3} value={form.description} onChange={set('description')} />
                <FieldDescription>Only you and Lost &amp; Found officers can read this.</FieldDescription>
              </Field>
            </FieldGroup>
          </FieldSet>

          <FieldSet>
            <FieldLegend>Where and when?</FieldLegend>
            <FieldGroup>
              <div className="grid gap-4 sm:grid-cols-3">
                <Field className="sm:col-span-1">
                  <FieldLabel htmlFor="building">Building</FieldLabel>
                  <Select required value={form.building} onValueChange={(v) => setForm((f) => ({ ...f, building: v }))}>
                    <SelectTrigger id="building" className="w-full">
                      <SelectValue placeholder="Choose" />
                    </SelectTrigger>
                    <SelectContent>
                      {BUILDINGS.map((b) => (
                        <SelectItem key={b} value={b}>
                          {b}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </Field>
                <Field>
                  <FieldLabel htmlFor="floor">Floor</FieldLabel>
                  <Input id="floor" maxLength={30} value={form.floor} onChange={set('floor')} />
                </Field>
                <Field>
                  <FieldLabel htmlFor="area">Area</FieldLabel>
                  <Input id="area" maxLength={60} placeholder="e.g. Main entrance" value={form.area} onChange={set('area')} />
                </Field>
              </div>
              <Field>
                <FieldLabel htmlFor="details">Location details</FieldLabel>
                <Input id="details" maxLength={300} value={form.details} onChange={set('details')} />
              </Field>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field>
                  <FieldLabel htmlFor="date">Date {found ? 'found' : 'lost'}</FieldLabel>
                  <Input id="date" type="date" required max={today()} value={form.date} onChange={set('date')} />
                </Field>
                <Field>
                  <FieldLabel htmlFor="approxTime">Approximate time</FieldLabel>
                  <Input id="approxTime" type="time" value={form.approxTime} onChange={set('approxTime')} />
                  <FieldDescription>Optional.</FieldDescription>
                </Field>
              </div>
              {found && (
                <Field>
                  <FieldLabel htmlFor="heldAt">Where is the item now?</FieldLabel>
                  <Input
                    id="heldAt"
                    maxLength={100}
                    placeholder="e.g. Security office, Building 5"
                    value={form.heldAt}
                    onChange={set('heldAt')}
                  />
                </Field>
              )}
            </FieldGroup>
          </FieldSet>

          {found && (
            <FieldSet>
              <FieldLegend>Verification questions</FieldLegend>
              <FieldDescription>
                Claimants must answer these. Ask about details only the owner would know (e.g. the name on a card),
                and write at least two if you can. Answers are stored hashed and never shown.
              </FieldDescription>
              <FieldGroup>
                {questions.map((q, i) => (
                  <div key={i} className="grid gap-2 sm:grid-cols-[1fr_12rem_auto]">
                    <Input
                      aria-label={`Question ${i + 1}`}
                      required
                      minLength={3}
                      maxLength={200}
                      placeholder="Question"
                      value={q.question}
                      onChange={(e) => setQuestion(i, 'question', e.target.value)}
                    />
                    <Input
                      aria-label={`Answer ${i + 1}`}
                      required
                      maxLength={100}
                      placeholder="Answer"
                      value={q.answer}
                      onChange={(e) => setQuestion(i, 'answer', e.target.value)}
                    />
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      aria-label={`Remove question ${i + 1}`}
                      disabled={questions.length === 1}
                      onClick={() => setQuestions((qs) => qs.filter((_, j) => j !== i))}
                    >
                      <Trash2Icon />
                    </Button>
                  </div>
                ))}
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="w-fit"
                  disabled={questions.length >= MAX_QUESTIONS}
                  onClick={() => setQuestions((qs) => [...qs, { question: '', answer: '' }])}
                >
                  <PlusIcon /> Add question
                </Button>
                <Field>
                  <FieldLabel htmlFor="serialNumber">Serial number</FieldLabel>
                  <Input id="serialNumber" maxLength={100} value={form.serialNumber} onChange={set('serialNumber')} />
                  <FieldDescription>Optional. Stored hashed, like the answers.</FieldDescription>
                </Field>
              </FieldGroup>
            </FieldSet>
          )}

          <FieldSet>
            <FieldLegend>Photos</FieldLegend>
            <FieldDescription>
              Up to {MAX_PHOTOS} JPEG or PNG photos, 5 MB each. Only you and officers can see them.
            </FieldDescription>
            <div className="flex flex-wrap gap-3">
              {previews.map((url, i) => (
                <div key={url} className="relative size-24 overflow-hidden rounded-md border">
                  <img src={url} alt={`Photo ${i + 1}`} className="size-full object-cover" />
                  <button
                    type="button"
                    aria-label={`Remove photo ${i + 1}`}
                    className="absolute top-1 right-1 rounded-full bg-background/80 p-0.5"
                    onClick={() => setPhotos((p) => p.filter((_, j) => j !== i))}
                  >
                    <XIcon className="size-4" />
                  </button>
                </div>
              ))}
              {photos.length < MAX_PHOTOS && (
                <label
                  className={cn(
                    'flex size-24 cursor-pointer flex-col items-center justify-center gap-1 rounded-md border border-dashed',
                    'text-xs text-muted-foreground hover:text-foreground',
                  )}
                >
                  <ImagePlusIcon className="size-5" />
                  Add photo
                  <input
                    type="file"
                    accept="image/jpeg,image/png"
                    multiple
                    className="sr-only"
                    onChange={(e) => {
                      addPhotos(e.target.files)
                      e.target.value = ''
                    }}
                  />
                </label>
              )}
            </div>
            {photoError && <p className="text-sm text-destructive">{photoError}</p>}
          </FieldSet>

          <Button type="submit" disabled={busy || !form.category || !form.building}>
            {busy && <Loader2Icon className="animate-spin" />}
            Submit {type} report
          </Button>
        </FieldGroup>
      </form>
    </div>
  )
}
