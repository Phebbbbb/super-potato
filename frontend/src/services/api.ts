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
    } else if (status === 409) {
      message.warning(detail || '数据已被他人修改，请刷新后重试')
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

// ===== 用户管理 =====
export const userApi = {
  list: (params?: any) => api.get('/users/', { params }),
  create: (data: any) => api.post('/users/', data),
  update: (id: string, data: any) => api.patch(`/users/${id}`, data),
  assign: (userId: string, clientId: string) => api.post(`/users/${userId}/assign`, { client_id: clientId }),
  unassign: (userId: string, clientId: string) => api.delete(`/users/${userId}/assign/${clientId}`),
}

// ===== 客户管理 =====
export const clientApi = {
  list: (params: any) => api.get('/clients/', { params }),
  create: (data: any) => api.post('/clients/', data),
  update: (id: string, data: any) => api.patch(`/clients/${id}`, data),
  delete: (id: string) => api.delete(`/clients/${id}`),
  availableStaff: () => api.get('/clients/staff/available'),
}

// ===== 原始凭证 =====
export const documentApi = {
  list: (params: any) => api.get('/documents/', { params }),
  get: (id: string) => api.get(`/documents/${id}`),
  upload: (formData: FormData) => api.post('/documents/upload', formData),
  delete: (id: string) => api.delete(`/documents/${id}`),
  channels: (clientId?: string) => api.get('/documents/collection-channels', { params: { client_id: clientId } }),
  emailCollect: (clientId: string) => api.post('/documents/email-collect', null, { params: { client_id: clientId } }),
  taxPull: (clientId: string, startDate?: string, endDate?: string) => api.post('/documents/tax-pull', null, { params: { client_id: clientId, start_date: startDate, end_date: endDate } }),
  collectionQR: (clientId?: string) => api.get('/documents/collection-qr', { params: { client_id: clientId } }),
  parse: (formData: FormData) => api.post('/documents/parse', formData),
  parseInvoice: (formData: FormData) => api.post('/documents/parse-invoice', formData),
  parseReceipt: (formData: FormData) => api.post('/documents/parse-receipt', formData),
  parseBankStatement: (formData: FormData) => api.post('/documents/parse-bank-statement', formData),
  reOCR: (id: string) => api.post(`/documents/${id}/re-ocr`),
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
  reverse: (id: string, reason?: string) => api.post(`/vouchers/${id}/reverse`, null, { params: { reason: reason || '' } }),
  rollback: (id: string) => api.post(`/vouchers/${id}/rollback`),
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
  missingFilings: (period: string) => api.get('/filings/missing-filings', { params: { period } }),
}

// ===== 自动申报引擎 =====
export const taxAutoApi = {
  file: (filingId: string, profile?: string) => api.post(`/tax-automation/file?filing_id=${filingId}&profile=${profile || 'generic'}`),
  profiles: () => api.get('/tax-automation/profiles'),
}

// ===== RPA 全自动加工链 =====
export const rpaApi = {
  autoProcess: (clientId: string) => api.post(`/rpa/auto-process?client_id=${clientId}`),
  autoSubmitFilings: (clientId: string) => api.post(`/rpa/auto-submit-filings?client_id=${clientId}`),
  autoCreateInvoices: (clientId: string) => api.post(`/rpa/auto-create-invoices?client_id=${clientId}`),
  autoIssueAllInvoices: (clientId: string) => api.post(`/rpa/auto-issue-all-invoices?client_id=${clientId}`),
  periodClose: (clientId: string, period?: string) =>
    api.post(`/rpa/period-close?client_id=${clientId}${period ? `&period=${period}` : ''}`),
  periodCloseRiskCheck: (clientId: string, period?: string) =>
    api.get(`/rpa/period-close/risk-check/${clientId}${period ? `?period=${period}` : ''}`),
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

// ===== 记账追溯 =====
export const traceApi = {
  chain: (targetType: string, targetId: string) => api.get(`/trace/${targetType}/${targetId}`),
}

// ===== 财务报表 =====
export const reportApi = {
  dashboard: () => api.get('/reports/dashboard'),
  automationRate: () => api.get('/reports/automation-rate'),
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
  generate: (data: any) => api.post('/reports/generate', data),
}

// ===== 预测分析 =====
export const predictiveApi = {
  analytics: (clientId: string, horizon = 6) =>
    api.get('/predictive/analytics', { params: { client_id: clientId, horizon } }),
  summary: (clientId: string) =>
    api.get('/predictive/summary', { params: { client_id: clientId } }),
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
  autoGenerateVouchers: (accountId: string, period: string) => api.post(`/bank/auto-generate-vouchers/${accountId}?period=${period}`),
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
  rules: () => api.get('/audit/rules'),
  batchAudit: (data: any) => api.post('/audit/batch-audit', data),
}

// ===== 数电票开票 =====
export const invoiceApi = {
  list: (params: any) => api.get('/invoices/', { params }),
  get: (id: string) => api.get(`/invoices/${id}`),
  create: (data: any) => api.post('/invoices/', data),
  issue: (id: string) => api.post(`/invoices/${id}/issue`),
  delete: (id: string) => api.delete(`/invoices/${id}`),
  riskCheck: (data: any) => api.post('/invoices/risk-check', data),
}

// ===== AI 税务顾问 =====
export const agentApi = {
  chat: (data: any) => api.post('/agent/chat', data),
  ragSearch: (q: string, topK?: number) => api.get('/agent/rag/search', { params: { q, top_k: topK || 5 } }),
  search: (q: string, collection?: string, topK?: number) =>
    api.get('/agent/search', { params: { q, collection: collection || 'all', top_k: topK || 20 } }),
}

// ===== 税务风控 =====
export const taxApi = {
  calendar: (params: any) => api.get('/tax/calendar', { params }),
  riskCheck: (params: any) => api.post('/agent/risk-check', null, { params }),
  riskSummary: () => api.get('/agent/risk-summary'),
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
  list: (limit?: number, source?: string) => api.get('/announcements/', { params: { limit: limit || 10, ...(source ? { source } : {}) } }),
  sources: () => api.get('/announcements/sources'),
  refresh: () => api.post('/announcements/refresh'),
}

// ===== 消息通知 =====
export const notificationApi = {
  list: (params?: any) => api.get('/notifications/', { params }),
  count: () => api.get('/notifications/count'),
  markRead: (id: string) => api.patch(`/notifications/${id}/read`),
  markAllRead: () => api.patch('/notifications/read-all'),
  send: (data: any) => api.post('/notifications/send', data),
  templates: () => api.get('/notifications/templates'),
  sendTest: (data: any) => api.post('/notifications/send-test', data),
}

// ===== 固定资产 =====
export const fixedAssetApi = {
  list: (params?: any) => api.get('/fixed-assets/', { params }),
  create: (data: any) => api.post('/fixed-assets/', data),
  update: (id: string, data: any) => api.patch(`/fixed-assets/${id}`, data),
  delete: (id: string) => api.delete(`/fixed-assets/${id}`),
  runDepreciation: (clientId: string, period?: string) => api.post(`/fixed-assets/run-depreciation?client_id=${clientId}${period ? `&period=${period}` : ''}`),
}

// ===== 合同管理 =====
export const contractApi = {
  list: (params?: any) => api.get('/contracts/', { params }),
  templates: () => api.get('/contracts/templates'),
  create: (data: any) => api.post('/contracts/', data),
  createFromTemplate: (templateId: string, data: any) => api.post(`/contracts/from-template/${templateId}`, data),
  update: (id: string, data: any) => api.patch(`/contracts/${id}`, data),
  delete: (id: string) => api.delete(`/contracts/${id}`),
  sendEsign: (id: string, data: any) => api.post(`/contracts/${id}/esign`, data),
  updateEsignStatus: (id: string, data: any) => api.patch(`/contracts/${id}/esign-status`, data),
  esignLog: (id: string) => api.get(`/contracts/${id}/esign-log`),
}

// ===== 系统运维 =====
export const systemApi = {
  backup: () => api.post('/system/backup'),
  restore: (backupFile: string) => api.post(`/system/restore?backup_file=${backupFile}`),
}

// ===== 发票真伪查验 =====
export const verifyApi = {
  verify: (data: any) => api.post('/invoice-verify/verify', data),
  verifyBatch: (data: any) => api.post('/invoice-verify/verify/batch', data),
  verifySystemInvoice: (invoiceId: string) => api.post(`/invoice-verify/verify/${invoiceId}`),
}

// ===== 批量自动化 =====
export const batchApi = {
  batchFiling: (data: any) => api.post('/batch/batch-filing', data),
  batchInvoice: (data: any) => api.post('/batch/batch-invoice', data),
  batchAllClients: (operation: string, profile?: string) =>
    api.post(`/batch/batch-all-clients?operation=${operation}&profile=${profile || 'generic'}`),
  getJobStatus: (jobId: string) => api.get(`/batch/job/${jobId}`),
  poolStats: () => api.get('/batch/pool-stats'),
}

// ===== 预检 + 税务优化 =====
export const precheckApi = {
  check: (clientId: string, period?: string) => api.get(`/precheck/${clientId}${period ? `?period=${period}` : ''}`),
  batchCheck: (clientIds?: string[]) => api.post('/precheck/batch', { client_ids: clientIds || [] }),
  optimize: (clientId: string, period?: string) => api.get(`/optimize/${clientId}${period ? `?period=${period}` : ''}`),
  batchOptimize: (clientIds?: string[]) => api.post('/optimize/batch', { client_ids: clientIds || [] }),
  dpOptimize: (clientId: string) => api.get(`/dp-optimize/${clientId}`),
  cliffCheck: (clientId: string) => api.get(`/cliff-check/${clientId}`),
}

// ===== 自学习引擎 =====
export const learningApi = {
  stats: () => api.get('/feedback/self-learning/stats'),
  preview: (data: any) => api.post('/feedback/self-learning/preview', data),
}

// ===== 异常检测引擎 =====
export const anomalyApi = {
  check: (clientId: string, period?: string) => api.get(`/anomaly/${clientId}${period ? `?period=${period}` : ''}`),
  batchCheck: (period?: string) => api.get(`/anomaly/batch${period ? `?period=${period}` : ''}`),
}

// ===== 智能优先级引擎 =====
export const priorityApi = {
  client: (clientId: string) => api.get(`/priority/${clientId}`),
  queue: () => api.get('/priority/queue'),
  worklist: (topN?: number) => api.get(`/priority/worklist${topN ? `?top_n=${topN}` : ''}`),
}

// ===== 检查点引擎 =====
export const checkpointApi = {
  list: () => api.get('/checkpoints'),
  stalled: () => api.get('/checkpoints/stalled'),
  recover: (runId: string) => api.post(`/checkpoints/${runId}/recover`),
}

// ===== 订阅管理 =====
export const subscriptionApi = {
  list: () => api.get('/subscriptions'),
  get: (clientId: string) => api.get(`/subscriptions/${clientId}`),
  trial: (clientId: string, phone: string) => api.post(`/subscriptions/${clientId}/trial?phone=${phone}`),
  upgrade: (clientId: string, phone: string) => api.post(`/subscriptions/${clientId}/upgrade?phone=${phone}`),
  renew: (subscriptionId: string) => api.post(`/subscriptions/${subscriptionId}/renew`),
}

// ===== 人员使用状态 =====
export const staffApi = {
  usage: () => api.get('/staff/usage'),
  loginHistory: (userId?: string, limit?: number) => api.get(`/staff/login-history${userId ? `?user_id=${userId}` : ''}${limit ? `${userId ? '&' : '?'}limit=${limit}` : ''}`),
}

// ===== 服务端-客户端交互 =====
export const interactionApi = {
  sendToClient: (data: { client_id: string; title: string; message: string; link?: string }) =>
    api.post('/interactions/send-to-client', data),
  feedback: (data: { title: string; message: string }) =>
    api.post('/interactions/feedback', data),
  serviceMessages: (limit?: number) =>
    api.get('/interactions/service-messages', { params: { limit: limit || 50 } }),
  clientMessages: (limit?: number) =>
    api.get('/interactions/client-messages', { params: { limit: limit || 50 } }),
}

// ===== 微信绑定 =====
export const wechatApi = {
  authorizeUrl: () => api.get('/wechat/authorize-url'),
  bind: (data: { openid: string; nickname?: string; avatar?: string }) =>
    api.post('/wechat/bind', data),
  status: () => api.get('/wechat/status'),
  unbind: () => api.post('/wechat/unbind'),
}

// ===== 自动化采集 =====
export const automationApi = {
  // 热文件夹
  hotFolders: () => api.get('/automation/hot-folders'),
  addHotFolder: (data: any) => api.post('/automation/hot-folders', data),
  removeHotFolder: (id: string) => api.delete(`/automation/hot-folders/${id}`),
  toggleHotFolder: (id: string, enabled: boolean) => api.patch(`/automation/hot-folders/${id}/toggle`, { enabled }),
  // 邮件采集
  emailCollectors: () => api.get('/automation/email-collectors'),
  addEmailCollector: (data: any) => api.post('/automation/email-collectors', data),
  removeEmailCollector: (id: string) => api.delete(`/automation/email-collectors/${id}`),
  toggleEmailCollector: (id: string, enabled: boolean) => api.patch(`/automation/email-collectors/${id}/toggle`, { enabled }),
  testEmailCollector: (id: string) => api.post(`/automation/email-collectors/${id}/test`),
  // ZIP 导入
  zipImport: (formData: FormData) => api.post('/automation/zip-import', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }),
  // Webhook
  webhooks: () => api.get('/automation/webhooks'),
  addWebhook: (data: any) => api.post('/automation/webhooks', data),
  removeWebhook: (id: string) => api.delete(`/automation/webhooks/${id}`),
  toggleWebhook: (id: string, enabled: boolean) => api.patch(`/automation/webhooks/${id}/toggle`, { enabled }),
  // 综合状态
  status: () => api.get('/automation/status'),
}

// ===== 换机助手 =====
export const migrationApi = {
  exportExcel: () => api.get('/migration/export', { responseType: 'blob' }),
  exportFull: () => api.get('/migration/export-full'),
  downloadTemplate: () => api.get('/migration/template', { responseType: 'blob' }),
  preview: (file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return api.post('/migration/preview', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  import: (file: File, conflictStrategy: string = 'skip') => {
    const fd = new FormData()
    fd.append('file', file)
    return api.post(`/migration/import?conflict_strategy=${conflictStrategy}`, fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  autoYqy: (username: string, password: string, orgName?: string, conflictStrategy: string = 'skip') => {
    const params = new URLSearchParams({ username, password, conflict_strategy: conflictStrategy })
    if (orgName) params.append('org_name', orgName)
    return api.post(`/migration/auto-yqy?${params.toString()}`)
  },
}

// ===== 工商年报 =====
export const annualReportApi = {
  list: (params?: any) => api.get('/annual-reports/', { params }),
  get: (id: string) => api.get(`/annual-reports/${id}`),
  create: (data: any) => api.post('/annual-reports/', data),
  update: (id: string, data: any) => api.patch(`/annual-reports/${id}`, data),
  delete: (id: string) => api.delete(`/annual-reports/${id}`),
  checkMissing: (clientId: string) => api.get('/annual-reports/check/missing', { params: { client_id: clientId } }),
}

// ===== 工商中心 =====
export const businessApi = {
  // 工商注册
  listRegistrations: (params?: any) => api.get('/business/registration', { params }),
  createRegistration: (data: any) => api.post('/business/registration', data),
  updateRegistration: (id: string, data: any) => api.patch(`/business/registration/${id}`, data),
  // 工商注销
  listDeregistrations: (params?: any) => api.get('/business/deregistration', { params }),
  createDeregistration: (data: any) => api.post('/business/deregistration', data),
  // 股权变更
  listEquityChanges: (params?: any) => api.get('/business/equity-change', { params }),
  createEquityChange: (data: any) => api.post('/business/equity-change', data),
  // 工商查询
  lookup: (data: any) => api.post('/business/lookup', data),
  nameSuggestions: (data: any) => api.post('/business/name-suggestions', data),
  // AI 工商助手
  agent: (data: any) => api.post('/business/agent', data),
  // 自动化
  autoAnnualReport: (data: any) => api.post('/business/auto/annual-report', data),
  autoLookup: (data: any) => api.post('/business/auto/lookup', data),
  autoGenerateForm: (data: any) => api.post('/business/auto/generate-form', data),
  autoLearningStats: () => api.get('/business/auto/learning-stats'),
  // 操作日志
  auditLog: (params?: any) => api.get('/business/audit-log', { params }),
  // 工作流
  createWorkflow: (data: any) => api.post('/business/workflow/create', data),
  getWorkflow: (instanceId: string) => api.get(`/business/workflow/${instanceId}`),
  updateWorkflowNode: (instanceId: string, nodeId: string, data: any) =>
    api.patch(`/business/workflow/${instanceId}/node/${nodeId}`, data),
  advanceWorkflowNode: (instanceId: string, nodeId: string) =>
    api.post(`/business/workflow/${instanceId}/node/${nodeId}/advance`),
  submitWorkflow: (instanceId: string) => api.post(`/business/workflow/${instanceId}/submit`),
  listWorkflows: (taskType?: string) => api.get('/business/workflows', { params: { task_type: taskType } }),
  getWorkflowTemplate: (taskType: string) => api.get(`/business/workflow/templates/${taskType}`),
}

// ===== 汇算清缴 =====
export const taxSettlementApi = {
  preview: (params?: any) => api.get('/tax/settlement-preview', { params }),
}

export default api
