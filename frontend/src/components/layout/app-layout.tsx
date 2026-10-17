import { SearchIcon } from 'lucide-react'
import { Link, NavLink, Outlet } from 'react-router'

import { UserMenu } from '@/components/layout/user-menu'
import { VerifyBanner } from '@/components/layout/verify-banner'
import { cn } from '@/lib/utils'

const NAV = [
  { to: '/search', label: 'Search' },
  { to: '/report', label: 'Report item' },
  { to: '/my-reports', label: 'My reports' },
  { to: '/notifications', label: 'Notifications' },
  { to: '/categories', label: 'Categories' },
]

export function AppLayout() {
  return (
    <div className="flex min-h-svh flex-col bg-background">
      <header className="border-b">
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-6 px-4">
          <Link to="/" className="flex items-center gap-2 font-semibold">
            <SearchIcon className="size-5" />
            ReFind
          </Link>
          <nav className="hidden flex-1 items-center gap-1 md:flex">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  cn(
                    'rounded-md px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground',
                    isActive && 'bg-muted text-foreground',
                  )
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto">
            <UserMenu />
          </div>
        </div>
      </header>
      <VerifyBanner />
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8">
        <Outlet />
      </main>
    </div>
  )
}
