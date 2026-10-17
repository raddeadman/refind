// JWT storage. Owner: Habib (login/register pages build on this).
const KEY = 'refind.token'

export function getToken(): string | null {
  try {
    return localStorage.getItem(KEY)
  } catch {
    return null
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(KEY, token)
    else localStorage.removeItem(KEY)
  } catch {
    // storage unavailable (private mode): user stays logged out
  }
}
