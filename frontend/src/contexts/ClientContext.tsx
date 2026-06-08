import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react'

interface ClientInfo {
  id: string
  name: string
  tax_no: string
}

interface ClientContextType {
  currentClientId: string
  clientList: ClientInfo[]
  switchClient: (id: string) => void
  loadClients: () => Promise<void>
}

const ClientContext = createContext<ClientContextType>({
  currentClientId: '',
  clientList: [],
  switchClient: () => {},
  loadClients: async () => {},
})

export function ClientProvider({ children }: { children: ReactNode }) {
  const [currentClientId, setCurrentClientId] = useState(
    () => localStorage.getItem('current_client_id') || ''
  )
  const [clientList, setClientList] = useState<ClientInfo[]>([])

  const loadClients = useCallback(async () => {
    const token = localStorage.getItem('token')
    if (!token) return
    try {
      const res = await fetch('/api/clients/?page_size=200', {
        headers: { Authorization: `Bearer ${token}` },
      })
      const data = await res.json()
      if (data.items) {
        setClientList(data.items.map((c: any) => ({ id: c.id, name: c.name, tax_no: c.tax_no })))
      }
    } catch { /* silent */ }
  }, [])

  const switchClient = (id: string) => {
    setCurrentClientId(id)
    localStorage.setItem('current_client_id', id)
  }

  useEffect(() => { loadClients() }, [loadClients])

  return (
    <ClientContext.Provider value={{ currentClientId, clientList, switchClient, loadClients }}>
      {children}
    </ClientContext.Provider>
  )
}

export const useClient = () => useContext(ClientContext)
