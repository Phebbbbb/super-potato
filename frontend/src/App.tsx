import { Routes, Route, Navigate } from 'react-router-dom'
import { ClientProvider } from './contexts/ClientContext'
import MainLayout from './components/MainLayout'
import Dashboard from './pages/Dashboard'
import Documents from './pages/Documents'

import TaxFilings from './pages/TaxFilings'
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
import FixedAssets from './pages/FixedAssets'
import Invoicing from './pages/Invoicing'
import Contracts from './pages/Contracts'
import BusinessCenter from './pages/BusinessCenter'
import TaxSettlement from './pages/TaxSettlement'
import PrintCenter from './pages/PrintCenter'
import Guide from './pages/Guide'
import OperationLog from './pages/OperationLog'
import Interactions from './pages/Interactions'
import Migration from './pages/Migration'
import Announcements from './pages/Announcements'
import MissingFilings from './pages/MissingFilings'
import PeriodClose from './pages/PeriodClose'
import Automation from './pages/Automation'
import BatchAutomation from './pages/BatchAutomation'
import PrecheckOptimize from './pages/PrecheckOptimize'
import InvoiceVerify from './pages/InvoiceVerify'
import Subscriptions from './pages/Subscriptions'


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

          <Route path="tax-filings" element={<TaxFilings />} />
          <Route path="reports" element={<Reports />} />
          <Route path="settings" element={<Settings />} />
          <Route path="payroll" element={<Payroll />} />
          <Route path="bank-reconciliation" element={<BankReconciliation />} />
          <Route path="field-tasks" element={<FieldTasks />} />
          <Route path="ai-agent" element={<AIAgent />} />
          <Route path="tax-risk" element={<TaxRisk />} />
          <Route path="audit" element={<Audit />} />
          <Route path="invoicing" element={<Invoicing />} />
          <Route path="fixed-assets" element={<FixedAssets />} />
          <Route path="contracts" element={<Contracts />} />
          <Route path="business-center" element={<BusinessCenter />} />
          <Route path="tax-settlement" element={<TaxSettlement />} />
          <Route path="missing-filings" element={<MissingFilings />} />
          <Route path="period-close" element={<PeriodClose />} />
          <Route path="print-center" element={<PrintCenter />} />
          <Route path="guide" element={<Guide />} />
          <Route path="operation-log" element={<OperationLog />} />
          <Route path="interactions" element={<Interactions />} />
          <Route path="migration" element={<Migration />} />
          <Route path="announcements" element={<Announcements />} />
          <Route path="automation" element={<Automation />} />
          <Route path="batch-automation" element={<BatchAutomation />} />
          <Route path="precheck-optimize" element={<PrecheckOptimize />} />
          <Route path="invoice-verify" element={<InvoiceVerify />} />
          <Route path="subscriptions" element={<Subscriptions />} />

        </Route>
      </Routes>
    </ClientProvider>
  )
}
