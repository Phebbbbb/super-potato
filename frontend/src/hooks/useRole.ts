import { useMemo } from 'react'

interface User {
  id: string
  username: string
  display_name: string
  role: string
}

export function getUser(): User | null {
  try {
    const s = localStorage.getItem('user')
    return s ? JSON.parse(s) : null
  } catch {
    return null
  }
}

/** Paths where client users have full (non-read-only) access */
const CLIENT_ACTIVE_PATHS = ['/documents', '/ai-agent']

export function useRole() {
  const user = useMemo(() => getUser(), [])
  const role = user?.role ?? ''
  const isClient = role === 'client'
  return { user, role, isClient }
}

/** Whether a given route path is read-only for client users */
export function isReadOnlyForClient(path: string): boolean {
  const user = getUser()
  if (!user || user.role !== 'client') return false
  return !CLIENT_ACTIVE_PATHS.includes(path)
}
