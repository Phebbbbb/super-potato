import axios from 'axios'
import { message } from 'antd'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

// Auto-attach auth token to every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (res) => res.data,
  (err) => {
    const status = err.response?.status
    const code = err.response?.data?.code
    const detail = err.response?.data?.detail || err.message
    const retry = err.response?.data?.retry || false

    // 分级处理
    if (status === 401) {
      localStorage.removeItem('token')
      message.error('会话已过期，请重新登录')
      if (window.location.pathname !== '/login') {
        setTimeout(() => { window.location.href = '/login' }, 1500)
      }
    } else if (status === 423) {
      message.error(detail || '账户已被锁定，请稍后再试')
    } else if (status === 403) {
      message.warning('权限不足，请联系管理员')
    } else if (status === 429) {
      message.warning('请求过于频繁，请稍后再试')
    } else if (status && status >= 500) {
      message.error(`服务器异常: ${detail}`)
    } else if (code && code !== 'SUCCESS') {
      message.warning(`${detail}${retry ? ' (可重试)' : ''}`)
    }

    // 附加结构化信息，供调用方处理
    const enhanced = {
      ...err,
      code: code || `HTTP_${status}`,
      detail,
      retry: status === 429 ? true : retry,  // 429 总是可重试
      status,
    }
    return Promise.reject(enhanced)
  }
)

// ===== 客户管理 =====
export const clientApi = {
  list: (params: any) => api.get('/clients/', { params }),
  create: (data: any) => api.post('/clients/', data),
  update: (id: string, data: any) => api.patch(`/clients/${id}`, data),
  delete: (id: string) => api.delete(`/clients/${id}`),
}

// ===== 原始凭证 =====
export const documentApi = {
  list: (params: any) => api.get('/documents/', { params }),
  get: (id: string) => api.get(`/documents/${id}`),
  upload: (formData: FormData) => api.post('/documents/upload', formData),
  delete: (id: string) => api.delete(`/documents/${id}`),
}

// ===== 记账凭证 =====
export const voucherApi = {
  list: (params: any) => api.get('/vouchers/', { params }),
  get: (id: string) => api.get(`/vouchers/${id}`),
  create: (data: any) => api.post('/vouchers/', data),
  aiGenerate: (documentIds: string[], clientId?: string) => api.post('/vouchers/ai-generate', documentIds, { params: { client_id: clientId } }),
  update: (id: string, data: any) => api.patch(`/vouchers/${id}`, data),
  confirm: (id: string, data?: any) => api.patch(`/vouchers/${id}/confirm`, data || {}),
  batchConfirm: (ids: string[], reviewer?: string) => api.post('/vouchers/batch-confirm', ids, { params: { reviewer: reviewer || '批量审核' } }),
  delete: (id: string) => api.delete(`/vouchers/${id}`),
}

// ===== 纳税申报 =====
export const filingApi = {
  list: (params: any) => api.get('/filings/', { params }),
  get: (id: string) => api.get(`/filings/${id}`),
  create: (data: any) => api.post('/filings/', data),
  update: (id: string, data: any) => api.patch(`/filings/${id}`, data),
  delete: (id: string) => api.delete(`/filings/${id}`),
  preview: (data: any) => api.post('/filings/preview', data),
}

// ===== 自动申报引擎 =====
export const taxAutoApi = {
  file: (filingId: string, profile?: string) => api.post(`/tax-automation/file?filing_id=${filingId}&profile=${profile || 'generic'}`),
  profiles: () => api.get('/tax-automation/profiles'),
}

// ===== 人工反馈修正（各环节审核通道）=====
export const feedbackApi = {
  correctDocOCR: (docId: string, data: any) => api.patch(`/feedback/document/${docId}/ocr`, data),
  correctVoucherEntries: (voucherId: string, data: any) => api.patch(`/feedback/voucher/${voucherId}/entries`, data),
  rejectVoucher: (voucherId: string, data: any) => api.patch(`/feedback/voucher/${voucherId}/reject`, data),
  reviewFiling: (filingId: string, data: any) => api.patch(`/feedback/filing/${filingId}/review`, data),
  auditTrail: (targetType: string, targetId: string) => api.get(`/feedback/audit/${targetType}/${targetId}`),
}

// ===== 会计科目 =====
export const accountApi = {
  list: (params: any) => api.get('/accounts/', { params }),
  tree: () => api.get('/accounts/tree'),
  get: (id: string) => api.get(`/accounts/${id}`),
  create: (data: any) => api.post('/accounts/', data),
}

// ===== QR 追溯 =====
export const qrApi = {
  trace: (targetType: string, targetId: string) => api.get(`/qr/trace/${targetType}/${targetId}`),
  scan: (qrId: string) => api.get(`/qr/scan/${qrId}`),
  batchExport: (data: any) => api.post('/qr/batch-export', data),
}

// ===== 财务报表 =====
export const reportApi = {
  dashboard: () => api.get('/reports/dashboard'),
  generalLedger: (period: string) => {
    const [y, m] = period.split('-')
    const start = `${y}-${m}-01`
    const end = `${y}-${m}-${new Date(Number(y), Number(m), 0).getDate()}`
    return api.get('/reports/general-ledger', { params: { start_date: start, end_date: end } })
  },
  trialBalance: (period: string) => api.get('/reports/trial-balance', { params: { period } }),
  incomeStatement: (period: string) => api.get('/reports/income-statement', { params: { period } }),
  balanceSheet: (period: string) => api.get('/reports/balance-sheet', { params: { period } }),
  cashFlow: (period: string) => api.get('/reports/cash-flow', { params: { period } }),
  export: (reportType: string, period: string) => api.get('/reports/export', { params: { report_type: reportType, period } }),
}

// ===== 系统配置 =====
export const settingsApi = {
  get: (key: string) => api.get(`/settings/${key}`),
  update: (key: string, data: any) => api.patch(`/settings/${key}`, { config_value: data }),
}

// ===== 薪酬管理 =====
export const payrollApi = {
  listEmployees: (params: any) => api.get('/payroll/employees/', { params }),
  createEmployee: (data: any) => api.post('/payroll/employees/', data),
  updateEmployee: (id: string, data: any) => api.patch(`/payroll/employees/${id}`, data),
  listBatches: (params: any) => api.get('/payroll/batches/', { params }),
  getBatch: (id: string) => api.get(`/payroll/batches/${id}`),
  generateBatch: (data: any) => api.post('/payroll/batches/generate', data),
  confirmBatch: (id: string, data: any) => api.post(`/payroll/batches/${id}/confirm`, data),
  updateDetail: (batchId: string, detailId: string, data: any) => api.patch(`/payroll/batches/${batchId}/detail/${detailId}`, data),
}

// ===== 银行对账 =====
export const bankApi = {
  listAccounts: (params: any) => api.get('/bank/accounts/', { params }),
  createAccount: (data: any) => api.post('/bank/accounts/', data),
  listStatements: (params: any) => api.get('/bank/statements/', { params }),
  importStatements: (accountId: string, clientId: string, formData: FormData) =>
    api.post(`/bank/import?bank_account_id=${accountId}&client_id=${clientId}`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
  autoMatch: (accountId: string) => api.post(`/bank/auto-match/${accountId}`),
  manualMatch: (statementId: string, data: any) => api.post(`/bank/match/${statementId}`, data),
  unmatch: (statementId: string) => api.post(`/bank/unmatch/${statementId}`),
  reconciliation: (accountId: string) => api.get(`/bank/reconciliation/${accountId}`),
}

// ===== 外勤任务 =====
export const fieldTaskApi = {
  list: (params: any) => api.get('/field-tasks/', { params }),
  create: (data: any) => api.post('/field-tasks/', data),
  update: (id: string, data: any) => api.patch(`/field-tasks/${id}`, data),
  delete: (id: string) => api.delete(`/field-tasks/${id}`),
}

// ===== 内审中心 =====
export const auditApi = {
  summary: (params: any) => api.get('/audit/summary', { params }),
  pendingVouchers: (params: any) => api.get('/audit/pending-vouchers', { params }),
  recentAudits: (params: any) => api.get('/audit/recent-audits', { params }),
  logs: (params: any) => api.get('/audit/logs', { params }),
  exportLogs: (params: any) => api.get('/audit/logs/export', { params, responseType: 'blob' }),
}

// ===== 数电票开票 =====
export const invoiceApi = {
  list: (params: any) => api.get('/invoices/', { params }),
  get: (id: string) => api.get(`/invoices/${id}`),
  create: (data: any) => api.post('/invoices/', data),
  issue: (id: string) => api.post(`/invoices/${id}/issue`),
  delete: (id: string) => api.delete(`/invoices/${id}`),
}

// ===== AI 税务顾问 =====
export const agentApi = {
  chat: (data: any) => api.post('/agent/chat', data),
}

// ===== 税务风控 =====
export const taxApi = {
  calendar: (params: any) => api.get('/tax/calendar', { params }),
  riskCheck: (params: any) => api.get('/tax/risk-check', { params }),
}

// ===== 版本控制（财税 Git）=====
export const versionApi = {
  history: (targetType: string, targetId: string) => api.get(`/version/history/${targetType}/${targetId}`),
  diff: (targetType: string, targetId: string) => api.get(`/version/diff/${targetType}/${targetId}`),
  revert: (targetType: string, targetId: string, versionId: string) =>
    api.post(`/version/revert/${targetType}/${targetId}?version_id=${versionId}`),
  recent: (limit?: number) => api.get('/version/recent', { params: { limit: limit || 50 } }),
}

// ===== 官方公告 =====
export const announcementApi = {
  list: (limit?: number) => api.get('/announcements/', { params: { limit: limit || 10 } }),
  refresh: () => api.post('/announcements/refresh'),
}

// ===== 系统运维 =====
export const systemApi = {
  backup: () => api.post('/system/backup'),
  restore: (backupFile: string) => api.post(`/system/restore?backup_file=${backupFile}`),
}

export default api
