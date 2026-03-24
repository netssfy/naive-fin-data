import { createBrowserRouter, createHashRouter } from 'react-router-dom'
import { AppShell } from '@/components/layout/app-shell'
import { DashboardPage } from '@/pages/dashboard-page'
import { SettingsPage } from '@/pages/settings-page'
import { SeasonsPage } from '@/pages/seasons-page'

const routes = [
  {
    path: '/',
    element: <AppShell />,
    children: [
      {
        index: true,
        element: <SeasonsPage />,
      },
      {
        path: 'dashboard',
        element: <DashboardPage />,
      },
      {
        path: 'settings',
        element: <SettingsPage />,
      },
    ],
  },
]

const isFileProtocol = typeof window !== 'undefined' && window.location.protocol === 'file:'
export const router = (isFileProtocol ? createHashRouter : createBrowserRouter)(routes)