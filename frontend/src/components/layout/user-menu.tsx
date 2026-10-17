import { LogOutIcon, UserIcon } from 'lucide-react'
import { Link, useNavigate } from 'react-router'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useAuth } from '@/lib/auth-context'

export function UserMenu() {
  const { user, isLoading, signOut } = useAuth()
  const navigate = useNavigate()

  if (isLoading) return null
  if (!user) {
    return (
      <div className="flex items-center gap-2">
        <Button asChild size="sm" variant="ghost">
          <Link to="/login">Log in</Link>
        </Button>
        <Button asChild size="sm">
          <Link to="/register">Sign up</Link>
        </Button>
      </div>
    )
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm">
          <UserIcon />
          <span className="max-w-32 truncate">{user.name}</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel className="font-normal">
          <div className="font-medium">{user.name}</div>
          <div className="truncate text-xs text-muted-foreground">{user.email}</div>
          {user.role !== 'user' && (
            <Badge variant="secondary" className="mt-1.5 capitalize">
              {user.role}
            </Badge>
          )}
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link to="/my-reports">My reports</Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link to="/notifications">Notifications</Link>
        </DropdownMenuItem>
        {(user.role === 'officer' || user.role === 'admin') && (
          <DropdownMenuItem asChild>
            <Link to="/officer/claims">Claim review queue</Link>
          </DropdownMenuItem>
        )}
        {user.role === 'admin' && (
          <>
            <DropdownMenuItem asChild>
              <Link to="/admin/users">Manage users</Link>
            </DropdownMenuItem>
            <DropdownMenuItem asChild>
              <Link to="/admin/categories">Manage categories</Link>
            </DropdownMenuItem>
          </>
        )}
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onSelect={() => {
            signOut()
            navigate('/')
          }}
        >
          <LogOutIcon />
          Log out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
