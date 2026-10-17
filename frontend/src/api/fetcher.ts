import { getToken } from '@/lib/auth'

/** Error thrown for any non-2xx response; `detail` is FastAPI's message. */
export class ApiError extends Error {
  status: number
  detail: unknown

  constructor(status: number, detail: unknown) {
    super(typeof detail === 'string' ? detail : `Request failed (${status})`)
    this.status = status
    this.detail = detail
  }
}

/**
 * Every Orval-generated request goes through here: adds the JWT and
 * turns error responses into ApiError so React Query sees them as errors.
 */
export async function apiFetch<T>(url: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers)
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)

  const response = await fetch(url, { ...options, headers })
  const body = [204, 205, 304].includes(response.status) ? null : await response.json().catch(() => null)

  if (!response.ok) {
    throw new ApiError(response.status, body?.detail ?? body)
  }
  return { data: body, status: response.status, headers: response.headers } as T
}

/** A readable message for any error thrown by a generated hook. */
export function errorMessage(error: unknown, fallback = 'Something went wrong. Please try again.'): string {
  if (error instanceof ApiError) {
    // 422 from FastAPI: [{loc, msg, ...}, ...]
    if (Array.isArray(error.detail)) {
      return error.detail.map((d: { msg?: string }) => d.msg?.replace(/^Value error, /, '')).filter(Boolean).join('. ')
    }
    return error.message
  }
  if (error instanceof TypeError) return 'Cannot reach the server. Is the API running?'
  return fallback
}
