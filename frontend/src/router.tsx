import { createBrowserRouter } from 'react-router'

import { AppLayout } from '@/components/layout/app-layout'
import { RequireAuth } from '@/components/require-auth'
import { AuthCallbackPage } from '@/pages/auth-callback'
import { CategoriesPage } from '@/pages/categories'
import { HomePage } from '@/pages/home'
import { LoginPage } from '@/pages/login'
import { NotFoundPage } from '@/pages/not-found'
import { PlaceholderPage } from '@/pages/placeholder'
import { RegisterPage } from '@/pages/register'
import { VerifyEmailPage } from '@/pages/verify-email'

const staff = ['officer', 'admin'] as const

// Screens from proposal §6.1. Replace each PlaceholderPage as it is built.
export const router = createBrowserRouter([
  {
    element: <AppLayout />,
    children: [
      { index: true, element: <HomePage /> },
      { path: 'categories', element: <CategoriesPage /> },

      // Habib – auth & claims
      { path: 'login', element: <LoginPage /> },
      { path: 'register', element: <RegisterPage /> },
      { path: 'verify-email', element: <VerifyEmailPage /> },
      { path: 'auth/callback', element: <AuthCallbackPage /> },
      {
        path: 'items/:id/claim',
        element: <RequireAuth><PlaceholderPage title="Claim this item" owner="Habib" milestone="M5" /></RequireAuth>,
      },
      {
        path: 'officer/claims',
        element: <RequireAuth roles={[...staff]}><PlaceholderPage title="Claim review queue" owner="Habib" milestone="M5" /></RequireAuth>,
      },
      {
        path: 'officer/claims/:id/handover',
        element: <RequireAuth roles={[...staff]}><PlaceholderPage title="Record handover" owner="Habib" milestone="M5" /></RequireAuth>,
      },

      // Faisal – items
      { path: 'search', element: <PlaceholderPage title="Search found items" owner="Faisal" milestone="M3" /> },
      { path: 'items/:id', element: <PlaceholderPage title="Item detail" owner="Faisal" milestone="M7" /> },
      {
        path: 'report',
        element: <RequireAuth><PlaceholderPage title="Report an item" owner="Faisal" milestone="M3" /></RequireAuth>,
      },
      {
        path: 'my-reports',
        element: <RequireAuth><PlaceholderPage title="My reports" owner="Faisal" milestone="M7" /></RequireAuth>,
      },
      {
        path: 'admin/categories',
        element: <RequireAuth roles={['admin']}><PlaceholderPage title="Manage categories" owner="Faisal" milestone="M7" /></RequireAuth>,
      },

      // Abdullah – matching & admin
      {
        path: 'items/:id/matches',
        element: <RequireAuth><PlaceholderPage title="Possible matches" owner="Abdullah" milestone="M4" /></RequireAuth>,
      },
      {
        path: 'notifications',
        element: <RequireAuth><PlaceholderPage title="Notifications" owner="Abdullah" milestone="M4" /></RequireAuth>,
      },
      {
        path: 'admin/users',
        element: <RequireAuth roles={['admin']}><PlaceholderPage title="Manage users & roles" owner="Abdullah" milestone="M7" /></RequireAuth>,
      },

      { path: '*', element: <NotFoundPage /> },
    ],
  },
])
