import { createBrowserRouter } from 'react-router-dom'
import { AppShell } from '@/components/layout/app-shell'
import { DashboardPage } from '@/pages/dashboard-page'
import { SettingsPage } from '@/pages/settings-page'

export const router = createBrowserRouter([
  {
    path: '/',
    element: <AppShell />,
    children: [
      {
        index: true,
        element: <DashboardPage />,
      },
      {
        path: 'settings',
        element: <SettingsPage />,
      },
    ],
  },
])