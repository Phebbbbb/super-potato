import { Routes, Route, Navigate } from 'react-router-dom'
import { ClientProvider } from './contexts/ClientContext'
import MainLayout from './components/MainLayout'
import Dashboard from './pages/Dashboard'
import Documents from './pages/Documents'
import Vouchers from './pages/Vouchers'

import TaxFilings from './pages/TaxFilings'
import Trace from './pages/Trace'
import Reports from './pages/Reports'
import Settings from './pages/Settings'
import Login from './pages/Login'
import Clients from './pages/Clients'
import Payroll from './pages/Payroll'
import BankReconciliation from './pages/BankReconciliation'
import FieldTasks from './pages/FieldTasks'
import AIAgent from './pages/AIAgent'
import TaxRisk from './pages/TaxRisk'
import Audit from './pages/Audit'
import Invoicing from './pages/Invoicing'
import PrintCenter from './pages/PrintCenter'
import Guide from './pages/Guide'

export default function App() {
  return (
    <ClientProvider>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/" element={<MainLayout />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="clients" element={<Clients />} />
          <Route path="documents" element={<Documents />} />
          <Route path="vouchers" element={<Vouchers />} />

          <Route path="tax-filings" element={<TaxFilings />} />
          <Route path="trace" element={<Trace />} />
          <Route path="reports" element={<Reports />} />
          <Route path="settings" element={<Settings />} />
          <Route path="payroll" element={<Payroll />} />
          <Route path="bank-reconciliation" element={<BankReconciliation />} />
          <Route path="field-tasks" element={<FieldTasks />} />
          <Route path="ai-agent" element={<AIAgent />} />
          <Route path="tax-risk" element={<TaxRisk />} />
          <Route path="audit" element={<Audit />} />
          <Route path="invoicing" element={<Invoicing />} />
          <Route path="print-center" element={<PrintCenter />} />
          <Route path="guide" element={<Guide />} />
        </Route>
      </Routes>
    </ClientProvider>
  )
}
