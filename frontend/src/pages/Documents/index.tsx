import { useState, useEffect, useRef } from 'react'
import { Card, Upload, Table, Button, Space, Tag, Modal, Image, Input, Form, InputNumber, App, Descriptions, Typography, Result, Tooltip, Row, Col, Select, Drawer, Timeline, Spin, Empty, Steps, Tabs } from 'antd'
import { InboxOutlined, QrcodeOutlined, DeleteOutlined, EyeOutlined, EditOutlined, HistoryOutlined, RocketOutlined, CheckCircleOutlined, CloudDownloadOutlined, MailOutlined, ScanOutlined, UploadOutlined, RobotOutlined, CheckOutlined, SafetyCertificateOutlined, CloseOutlined, UndoOutlined, ArrowDownOutlined, ArrowUpOutlined, FileZipOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { useNavigate } from 'react-router-dom'
import { documentApi, feedbackApi, rpaApi, automationApi, traceApi, voucherApi } from '@/services/api'
import { useClient } from '@/contexts/ClientContext'
import { useRole } from '@/hooks/useRole'
import EmptyState from '@/components/EmptyState'
import SkeletonTable from '@/components/SkeletonTable'

const { Dragger } = Upload
const { Text } = Typography

export default function Documents() {
  // ===== 票据采集 state =====
  const [documents, setDocuments] = useState<any[]>([])
  const [docLoading, setDocLoading] = useState(false)
  const [detailOpen, setDetailOpen] = useState(false)
  const [ocrEditOpen, setOcrEditOpen] = useState(false)
  const [auditOpen, setAuditOpen] = useState(false)
  const [selectedDoc, setSelectedDoc] = useState<any>(null)
  const [auditTrail, setAuditTrail] = useState<any[]>([])
  const [ocrForm] = Form.useForm()

  // 上传批次追踪
  const [uploading, setUploading] = useState(false)
  const [uploadCount, setUploadCount] = useState(0)
  const uploadBatchRef = useRef<string[]>([])

  // 自动加工状态
  const [processing, setProcessing] = useState(false)
  const [processResult, setProcessResult] = useState<any>(null)

  // ===== 多渠道采集 state =====
  const [channelModal, setChannelModal] = useState<string | null>(null)
  const [channelLoading, setChannelLoading] = useState(false)
  const [channelResult, setChannelResult] = useState<any>(null)
  const [webhooks, setWebhooks] = useState<any[]>([])
  const [webhookPlatform, setWebhookPlatform] = useState<string>('wechat')
  const [webhookCreating, setWebhookCreating] = useState(false)

  const { currentClientId } = useClient()
  const { isClient } = useRole()
  const [activeTab, setActiveTab] = useState('docs')
  const navigate = useNavigate()
  const { message } = App.useApp()

  // 一键申报提交
  const [submitting, setSubmitting] = useState(false)
  const [submitResult, setSubmitResult] = useState<any>(null)

  // 记账追溯 Drawer
  const [traceDrawerOpen, setTraceDrawerOpen] = useState(false)
  const [traceLoading, setTraceLoading] = useState(false)
  const [traceChain, setTraceChain] = useState<any[]>([])
  const [traceTarget, setTraceTarget] = useState('')

  const showTrace = async (record: any) => {
    setTraceTarget(record.file_name || record.id)
    setTraceDrawerOpen(true)
    setTraceLoading(true)
    try {
      const res: any = await traceApi.chain('document', record.id)
      setTraceChain(res.chain || [])
    } catch { setTraceChain([]) }
    setTraceLoading(false)
  }

  // ===== ② 记账凭证生成 state =====
  const [vouchers, setVouchers] = useState<any[]>([])
  const [voucherLoading, setVoucherLoading] = useState(false)
  const [aiVoucherModalOpen, setAiVoucherModalOpen] = useState(false)
  const [selectedDocIds, setSelectedDocIds] = useState<string[]>([])
  const [voucherDetailOpen, setVoucherDetailOpen] = useState(false)
  const [selectedVoucher, setSelectedVoucher] = useState<any>(null)
  const [voucherEditOpen, setVoucherEditOpen] = useState(false)
  const [voucherEditForm] = Form.useForm()

  // ===== ③ 会计复核确认 state =====
  const [reviewerName, setReviewerName] = useState('')
  const [confirmLoading, setConfirmLoading] = useState(false)

  const fetchVouchers = async () => {
    setVoucherLoading(true)
    try {
      const res: any = await voucherApi.list({ page: 1, page_size: 20, client_id: currentClientId })
      setVouchers(res.items || [])
    } catch { /* ignore */ }
    setVoucherLoading(false)
  }

  useEffect(() => {
    if (!isClient) fetchVouchers()
  }, [currentClientId])

  const handleAIGenerateVoucher = async () => {
    if (selectedDocIds.length === 0) { message.warning('请先在上方选择原始凭证'); return }
    try {
      const res: any = await voucherApi.aiGenerate(selectedDocIds, currentClientId)
      message.success(`记账凭证 ${res.voucher_no} 已生成，请在下方复核`)
      setAiVoucherModalOpen(false)
      setSelectedDocIds([])
      fetchVouchers()
    } catch (e: any) { message.error(e?.response?.data?.detail || 'AI生成失败') }
  }

  const handleManualVoucher = () => {
    setSelectedVoucher(null)
    voucherEditForm.resetFields()
    voucherEditForm.setFieldsValue({
      summary: '',
      entries: [{ account_code: '', account_name: '', summary: '', debit: 0, credit: 0 }],
    })
    setVoucherEditOpen(true)
  }

  const handleEditVoucher = (record: any) => {
    setSelectedVoucher(record)
    const entries = record.entries || []
    voucherEditForm.setFieldsValue({
      summary: record.summary,
      entries: entries.map((e: any, i: number) => ({
        key: i, account_code: e.account_code, account_name: e.account_name,
        debit: e.debit, credit: e.credit, summary: e.summary,
      })),
    })
    setVoucherEditOpen(true)
  }

  const handleSaveVoucherEdit = async () => {
    const values = await voucherEditForm.validateFields()
    const entries = values.entries.map((e: any) => ({
      account_code: e.account_code, account_name: e.account_name,
      debit: e.debit || 0, credit: e.credit || 0, summary: e.summary || '',
    }))
    try {
      if (selectedVoucher?.id) {
        await feedbackApi.correctVoucherEntries(selectedVoucher.id, { summary: values.summary, entries })
        message.success('凭证已修正')
      } else {
        await voucherApi.create({
          summary: values.summary,
          voucher_date: values.voucher_date || new Date().toISOString().slice(0, 10),
          entries,
          client_id: currentClientId,
        })
        message.success('凭证创建成功')
      }
      setVoucherEditOpen(false)
      fetchVouchers()
    } catch (e: any) {
      const detail = e?.response?.data?.detail
      if (typeof detail === 'object' && detail?.diff) {
        message.error(`借贷不平衡: 差额 ¥${detail.diff}`)
      } else {
        message.error(typeof detail === 'string' ? detail : '保存失败')
      }
    }
  }

  const handleRollbackVoucher = async (record: any) => {
    try {
      await voucherApi.rollback(record.id)
      message.success(`凭证 ${record.voucher_no} 已回退至草稿`)
      fetchVouchers()
    } catch (e: any) { message.error(e?.response?.data?.detail || '回退失败') }
  }

  const handleReverseVoucher = (record: any) => {
    Modal.confirm({
      title: '红字冲销',
      content: `确定对凭证 ${record.voucher_no} 进行红字冲销吗？系统将自动生成反向冲销凭证，原凭证标记为"已冲销"。`,
      okText: '确认冲销',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          const res: any = await voucherApi.reverse(record.id, '冲正')
          message.success(res.message || '红字冲销凭证已生成')
          fetchVouchers()
        } catch (e: any) { message.error(e?.response?.data?.detail || '冲销失败') }
      },
    })
  }

  const handleDeleteVoucher = (record: any) => {
    Modal.confirm({
      title: '确认删除',
      content: `确定要删除凭证 ${record.voucher_no} 吗？此操作不可恢复。`,
      okText: '删除',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await voucherApi.delete(record.id)
          message.success(`凭证 ${record.voucher_no} 已删除`)
          fetchVouchers()
        } catch { message.error('删除失败') }
      },
    })
  }

  const handleReviewConfirm = async (voucher: any) => {
    if (!reviewerName.trim()) { message.warning('请输入审核人姓名（签章）'); return }
    Modal.confirm({
      title: '确认复核？',
      content: `凭证 ${voucher.voucher_no} 复核通过后将不可逆，无法再修改或删除。`,
      okText: '确认，不可逆',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        setConfirmLoading(true)
        try {
          await voucherApi.confirm(voucher.id, { reviewer: reviewerName })
          message.success(`凭证 ${voucher.voucher_no} 复核通过，${reviewerName} 已签章`)
          setReviewerName('')
          fetchVouchers()
        } catch (e: any) { message.error(e?.response?.data?.detail || '复核失败') }
        setConfirmLoading(false)
      },
    })
  }

  const handleReviewReject = async (voucher: any) => {
    if (!reviewerName.trim()) { message.warning('请输入审核人姓名'); return }
    Modal.confirm({
      title: '确认退回？',
      content: `凭证 ${voucher.voucher_no} 将退回至「待修正」状态，制单人需重新提交。`,
      okText: '确认退回',
      cancelText: '取消',
      onOk: async () => {
        try {
          await feedbackApi.rejectVoucher(voucher.id, { reason: `${reviewerName} 复核退回`, issues: ['需修正后重新提交'] })
          message.success(`凭证 ${voucher.voucher_no} 已退回`)
          setReviewerName('')
          fetchVouchers()
        } catch { message.error('退回失败') }
      },
    })
  }

  // ===== 票据采集 =====
  const fetchDocuments = async () => {
    setDocLoading(true)
    try {
      const res: any = await documentApi.list({ page: 1, page_size: 50, client_id: currentClientId })
      setDocuments(res.items || [])
    } catch { message.error('加载原始凭证失败') }
    setDocLoading(false)
  }

  useEffect(() => {
    fetchDocuments()
  }, [currentClientId])

  const saveHandlerRef = useRef(handleSaveVoucherEdit)
  saveHandlerRef.current = handleSaveVoucherEdit

  // 键盘快捷键
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey
      // Ctrl+S / Cmd+S: 保存凭证编辑
      if (mod && e.key === 's' && voucherEditOpen) {
        e.preventDefault()
        saveHandlerRef.current()
        return
      }
      // Escape: 关闭弹窗
      if (e.key === 'Escape') {
        if (voucherEditOpen) setVoucherEditOpen(false)
        else if (voucherDetailOpen) setVoucherDetailOpen(false)
        else if (aiVoucherModalOpen) setAiVoucherModalOpen(false)
        else if (detailOpen) setDetailOpen(false)
        else if (ocrEditOpen) setOcrEditOpen(false)
        else if (auditOpen) setAuditOpen(false)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [voucherEditOpen, voucherDetailOpen, aiVoucherModalOpen, detailOpen, ocrEditOpen, auditOpen])

  // 上传完成后自动触发全自动加工
  const handleUploadChange = (info: any) => {
    const { status, name } = info.file

    if (status === 'uploading') {
      if (!uploadBatchRef.current.includes(name)) {
        uploadBatchRef.current.push(name)
      }
      setUploading(true)
      setUploadCount(uploadBatchRef.current.length)
      return
    }

    if (status === 'done' || status === 'error') {
      uploadBatchRef.current = uploadBatchRef.current.filter(n => n !== name)
      setUploadCount(uploadBatchRef.current.length)

      if (uploadBatchRef.current.length === 0) {
        setUploading(false)
        fetchDocuments()

        if (info.file.status === 'done') {
          message.success(`${info.file.name} 上传成功并 OCR 识别完成`)
        }

        setTimeout(async () => {
          setProcessing(true)
          setProcessResult(null)
          try {
            const res: any = await rpaApi.autoProcess(currentClientId || '')
            setProcessResult(res)
            message.success(res.summary || '全自动加工完成')
            fetchDocuments()
          } catch (e: any) {
            message.error(e?.detail || e?.response?.data?.detail || '自动加工失败')
          }
          setProcessing(false)
        }, 3000)
      }
    }
  }

  const uploadProps = {
    name: 'file',
    multiple: true,
    action: '/api/documents/upload',
    data: { client_id: currentClientId || '' },
    showUploadList: true,
    onChange: handleUploadChange,
    beforeUpload: (file: File) => {
      const isValid = file.type.startsWith('image/') || file.type === 'application/pdf'
      if (!isValid) {
        message.error(`${file.name} 格式不支持，请上传 JPG/PNG/PDF`)
        return Upload.LIST_IGNORE
      }
      return true
    },
  }

  const handleManualProcess = async () => {
    if (!currentClientId) { message.warning('请先选择客户'); return }
    setProcessing(true)
    setProcessResult(null)
    try {
      const res: any = await rpaApi.autoProcess(currentClientId)
      setProcessResult(res)
      message.success(res.summary || '全自动加工完成')
      fetchDocuments()
    } catch (e: any) {
      message.error(e?.detail || e?.response?.data?.detail || '自动加工失败，请检查日志')
    }
    setProcessing(false)
  }

  const handleAutoSubmit = async () => {
    if (!currentClientId) { message.warning('请先选择客户'); return }
    setSubmitting(true)
    setSubmitResult(null)
    try {
      const res: any = await rpaApi.autoSubmitFilings(currentClientId)
      setSubmitResult(res)
      if (res.failed_count > 0) {
        message.warning(res.message || `提交完成：${res.success_count}/${res.total} 成功`)
      } else {
        message.success(res.message || '全部申报提交成功')
      }
    } catch (e: any) {
      message.error(e?.detail || e?.response?.data?.detail || '申报提交失败')
    }
    setSubmitting(false)
  }

  const goToFilings = () => {
    setProcessResult(null)
    navigate('/tax-filings')
  }

  const showDetail = (record: any) => {
    setSelectedDoc(record)
    setDetailOpen(true)
  }

  const handleOCREdit = (record: any) => {
    setSelectedDoc(record)
    const ocr = record.ocr_structured || {}
    ocrForm.setFieldsValue({
      invoice_code: ocr.invoice_code || '',
      invoice_no: ocr.invoice_no || '',
      date: ocr.date || '',
      seller_name: ocr.seller_name || '',
      buyer_name: ocr.buyer_name || '',
      amount_excluding_tax: ocr.amount_excluding_tax || 0,
      tax_amount: ocr.tax_amount || 0,
      total_amount: ocr.total_amount || 0,
    })
    setOcrEditOpen(true)
  }

  const handleOCRSave = async () => {
    const values = await ocrForm.validateFields()
    try {
      await feedbackApi.correctDocOCR(selectedDoc.id, { ocr_structured: values })
      message.success('OCR 数据已修正')
      setOcrEditOpen(false)
      fetchDocuments()
    } catch (e: any) { message.error(e?.response?.data?.detail || '修正失败') }
  }

  const showAudit = async (record: any) => {
    setSelectedDoc(record)
    try {
      const res: any = await feedbackApi.auditTrail('document', record.id)
      setAuditTrail(res.trail || [])
    } catch { setAuditTrail([]) }
    setAuditOpen(true)
  }

  const handleDocReOCR = async (record: any) => {
    try {
      await documentApi.reOCR(record.id)
      message.success(`${record.file_name} 已重新提交 OCR 识别`)
      fetchDocuments()
    } catch (e: any) { message.error(e?.response?.data?.detail || '重新识别失败') }
  }

  const handleDocDelete = async (record: any) => {
    Modal.confirm({
      title: '确认删除',
      content: `确定要删除 "${record.file_name}" 吗？`,
      onOk: async () => {
        try { await documentApi.delete(record.id); message.success('已删除'); fetchDocuments() }
        catch (e: any) { message.error('删除失败') }
      },
    })
  }

  const docColumns: ColumnsType<any> = [
    { title: '文件名', dataIndex: 'file_name', key: 'file_name', ellipsis: true },
    {
      title: '类型', dataIndex: 'doc_type', key: 'doc_type', width: 90,
      render: (t: string) => {
        const map: Record<string, string> = { invoice: '发票', receipt: '收据', bank_receipt: '银行回单', contract: '合同', tax_cert: '完税证明', other: '其他' }
        return <Tag>{map[t] || t}</Tag>
      },
    },
    {
      title: 'OCR', dataIndex: 'ocr_status', key: 'ocr_status', width: 80,
      render: (s: string) => <Tag color={s === 'done' ? 'green' : 'default'}>{s === 'done' ? '已识别' : '待识别'}</Tag>,
    },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 160, render: (v: string) => v?.slice(0, 19) },
    {
      title: '操作', key: 'actions', width: 310,
      render: (_: any, record: any) => (
        <Space size={4} wrap>
          <Button size="small" icon={<EyeOutlined />} onClick={() => showDetail(record)}>详情</Button>
          <Button size="small" icon={<EditOutlined />} onClick={() => handleOCREdit(record)}>修正</Button>
          <Button size="small" icon={<UndoOutlined />} onClick={() => handleDocReOCR(record)}>重新识别</Button>
          <Button size="small" icon={<HistoryOutlined />} onClick={() => showAudit(record)}>日志</Button>
          <Button size="small" icon={<HistoryOutlined />} onClick={() => showTrace(record)}>追溯</Button>
          <Button size="small" danger icon={<DeleteOutlined />} onClick={() => handleDocDelete(record)}>删除</Button>
        </Space>
      ),
    },
  ]

  // ===== 多渠道采集 =====
  const handleChannelAction = async (channel: string) => {
    setChannelResult(null)
    setChannelModal(channel)
    if (channel === 'webhook') {
      try {
        const res: any = await automationApi.webhooks()
        setWebhooks(res.configs || [])
      } catch { setWebhooks([]) }
    }
  }

  const handleAddWebhook = async () => {
    if (!currentClientId) { message.warning('请先选择客户'); return }
    setWebhookCreating(true)
    try {
      const res: any = await automationApi.addWebhook({
        platform: webhookPlatform,
        client_id: currentClientId,
        name: `${webhookPlatform === 'wechat' ? '微信' : '钉钉'}采集机器人`,
      })
      message.success(`Webhook 创建成功: ${res.full_webhook_url}`)
      setWebhooks(prev => [...prev, res])
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '创建失败')
    }
    setWebhookCreating(false)
  }

  const handleToggleWebhook = async (id: string, enabled: boolean) => {
    try {
      await automationApi.toggleWebhook(id, enabled)
      setWebhooks(prev => prev.map(w => w.id === id ? { ...w, enabled } : w))
      message.success(enabled ? '已启用' : '已停用')
    } catch { message.error('操作失败') }
  }

  const handleRemoveWebhook = async (id: string) => {
    try {
      await automationApi.removeWebhook(id)
      setWebhooks(prev => prev.filter(w => w.id !== id))
      message.success('已移除')
    } catch { message.error('移除失败') }
  }

  const handleEmailCollect = async () => {
    if (!currentClientId) { message.warning('请先选择客户'); return }
    setChannelLoading(true)
    try {
      const res: any = await documentApi.emailCollect(currentClientId)
      setChannelResult({ ...res, channel: 'email' })
      message.success(res.message || '邮件采集完成')
      fetchDocuments()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '邮件采集失败')
    }
    setChannelLoading(false)
  }

  const handleTaxPull = async () => {
    if (!currentClientId) { message.warning('请先选择客户'); return }
    setChannelLoading(true)
    try {
      const res: any = await documentApi.taxPull(currentClientId)
      setChannelResult({ ...res, channel: 'tax_pull' })
      message.success(res.message || '电子税务局拉取完成')
      fetchDocuments()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '拉取失败，请检查电子税务局连接')
    }
    setChannelLoading(false)
  }

  // ===== 主内容 =====
  const mainContent = (
        <div>
          {/* 客户端说明 */}
          {isClient && (
            <div style={{ marginBottom: 16, padding: '14px 18px', background: '#eff6ff', borderRadius: 8, border: '1px solid #bfdbfe' }}>
              <div style={{ fontSize: 14, fontWeight: 600, color: '#1e40af', marginBottom: 4 }}>
                <UploadOutlined style={{ marginRight: 6 }} />票据上传说明
              </div>
              <div style={{ fontSize: 13, color: '#3b82f6', lineHeight: 1.7 }}>
                请将您的<strong>发票、收据、银行回单</strong>等原始凭证通过下方上传区域提交。
                上传后系统将自动进行 OCR 识别，您可以在<strong>交互中心</strong>查看处理进度和反馈消息。
                如需开具数电票，请联系您的<strong>爻管家</strong>客服。
              </div>
            </div>
          )}

          {/* 多渠道采集 */}
          {!isClient && (
          <Row gutter={12} style={{ marginBottom: 16 }}>
            {[
              { key: 'manual', icon: <UploadOutlined style={{ fontSize: 22 }} />, name: '手动上传', desc: '拖拽/点击上传文件', color: '#2563eb', bg: '#eff6ff' },
              { key: 'email', icon: <MailOutlined style={{ fontSize: 22 }} />, name: '邮件采集', desc: '发票转发至专属邮箱自动入库', color: '#7c3aed', bg: '#f5f3ff' },
              { key: 'tax_pull', icon: <CloudDownloadOutlined style={{ fontSize: 22 }} />, name: '税务局拉取', desc: '自动登录电子税务局拉取进项发票', color: '#dc2626', bg: '#fef2f2' },
              { key: 'qr_scan', icon: <ScanOutlined style={{ fontSize: 22 }} />, name: '扫码采集', desc: '手机扫码拍照上传票据', color: '#16a34a', bg: '#f0fdf4' },
              { key: 'webhook', icon: <RobotOutlined style={{ fontSize: 22 }} />, name: '微信/钉钉', desc: '配置机器人自动接收群聊票据', color: '#0891b2', bg: '#ecfeff' },
              { key: 'zip', icon: <FileZipOutlined style={{ fontSize: 22 }} />, name: 'ZIP 导入', desc: '批量上传发票压缩包自动解压入库', color: '#d97706', bg: '#fffbeb' },
            ].map(ch => (
              <Col xs={12} sm={8} md={6} lg={4} key={ch.key}>
                <Card
                  hoverable
                  size="small"
                  style={{
                    textAlign: 'center',
                    borderColor: ch.key === 'manual' ? ch.color : undefined,
                    borderWidth: ch.key === 'manual' ? 2 : 1,
                    cursor: 'pointer',
                  }}
                  bodyStyle={{ padding: '12px 8px' }}
                  onClick={() => ch.key === 'manual' ? null : handleChannelAction(ch.key)}
                >
                  <div style={{ color: ch.color, marginBottom: 4 }}>{ch.icon}</div>
                  <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 2 }}>{ch.name}</div>
                  <div style={{ fontSize: 11, color: '#94a3b8', lineHeight: 1.3 }}>{ch.desc}</div>
                </Card>
              </Col>
            ))}
          </Row>
          )}

          {/* 手动上传区 */}
          <Card style={{ marginBottom: 24 }}>
            <Dragger {...uploadProps} disabled={uploading}>
              <p className="ant-upload-drag-icon"><InboxOutlined /></p>
              <p className="ant-upload-text" style={{ fontSize: 16 }}>
                {uploading ? `正在上传 ${uploadCount} 个文件...` : '点击或拖拽文件/文件夹到此区域'}
              </p>
              <p className="ant-upload-hint">
                {isClient
                  ? '支持 JPG/PNG/PDF 批量上传 · 上传后自动 OCR 识别 · 爻管家将为您处理后续流程'
                  : '支持 JPG/PNG/PDF 批量上传 · 上传后自动 OCR 识别 · 完成自动触发全流程加工'}
              </p>
            </Dragger>
          </Card>

          {/* 自动处理结果 */}
          {processResult && !isClient && (
            <Card style={{ marginBottom: 24, borderColor: '#2563eb' }}>
              <Result
                status="success"
                title="全自动加工完成！"
                subTitle={processResult.summary}
                extra={[
                  <Button type="primary" key="submit" onClick={handleAutoSubmit}
                    loading={submitting} icon={<RocketOutlined />}
                    disabled={!processResult.filings_created}
                    style={{ background: '#16a34a', borderColor: '#16a34a' }}>
                    一键申报提交（自动提交到电子税务局）
                  </Button>,
                  <Button key="review" onClick={goToFilings} icon={<CheckCircleOutlined />}>
                    前往报税中心人工审核
                  </Button>,
                  <Button key="close" onClick={() => { setProcessResult(null); setSubmitResult(null) }}>关闭</Button>,
                ]}
              />
              {submitResult && (
                <div style={{ maxWidth: 560, margin: '0 auto 16px', padding: 16, background: '#f8fafc', borderRadius: 8, border: '1px solid #e2e8f0' }}>
                  <Text strong style={{ fontSize: 14, color: submitResult.failed_count > 0 ? '#d97706' : '#16a34a' }}>
                    {submitResult.message}
                  </Text>
                  {(submitResult.results || []).map((r: any, i: number) => (
                    <div key={i} style={{ fontSize: 12, margin: '6px 0', padding: '6px 8px', background: r.success ? '#f0fdf4' : '#fef2f2', borderRadius: 4 }}>
                      <span>{r.success ? '✅' : '❌'} <b>{r.tax_type}</b> {r.period}</span>
                      <div style={{ color: r.success ? '#16a34a' : '#dc2626' }}>{r.message}</div>
                      {!r.success && r.failed_step && (
                        <div style={{ color: '#9ca3af', marginTop: 2 }}>
                          失败步骤: {r.failed_step} | 已完成: {(r.steps_completed || []).join(' → ') || '无'}
                        </div>
                      )}
                      {r.screenshots && r.screenshots.length > 0 && (
                        <div style={{ marginTop: 4 }}>
                          {r.screenshots.map((s: string, si: number) => (
                            <Tooltip key={si} title="查看截图">
                              <Button type="link" size="small" onClick={() => Modal.info({ title: '申报截图', icon: null, width: 800, content: <Image src={`/${s}`} style={{ width: '100%' }} /> })}>
                                截图{si + 1}
                              </Button>
                            </Tooltip>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
              <div style={{ maxWidth: 500, margin: '0 auto' }}>
                {(processResult.details || []).map((d: string, i: number) => (
                  <p key={i} style={{ fontSize: 13, fontFamily: 'monospace', margin: '2px 0' }}>{d}</p>
                ))}
              </div>
            </Card>
          )}

          {/* 票据列表 */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16, marginTop: 16 }}>
            <Text strong style={{ fontSize: 15 }}>票据列表 ({documents.length})</Text>
          </div>

          {docLoading ? (
            <SkeletonTable rows={6} columns={5} />
          ) : documents.length === 0 ? (
            <Card>
              <EmptyState
                title="暂无票据"
                description="点击或拖拽文件到上方区域上传，支持 JPG/PNG/PDF 批量上传"
                icon={<InboxOutlined style={{ fontSize: 64, color: '#d9d9d9' }} />}
              />
            </Card>
          ) : (
            <Table
              dataSource={documents}
              columns={docColumns}
              rowKey="id"
              size="middle"
              locale={{ emptyText: '暂无票据' }}
              scroll={{ x: 900 }}
            />
          )}
        </div>
      )

  // 统计
  const ocrDoneCount = documents.filter(d => d.ocr_status === 'done').length

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <div>
          <h2 style={{ margin: 0 }}>记账业务</h2>
          <Text type="secondary" style={{ fontSize: 12 }}>
            全流程：原始凭证 → 记账凭证 → 会计复核
          </Text>
        </div>
        <Space size={12}>
          <Tag color="blue">{documents.length} 凭证</Tag>
          {ocrDoneCount > 0 && <Tag color="green">{ocrDoneCount} 已识别</Tag>}
        </Space>
      </div>

      <Steps
        size="small"
        current={activeTab === 'docs' ? 0 : activeTab === 'vouchers' ? 1 : 2}
        style={{ marginBottom: 20 }}
        items={[
          { title: '原始凭证入库', description: <><UndoOutlined style={{ color: '#16a34a', marginRight: 4 }} />可逆：可删除/重新识别</> },
          { title: '记账凭证生成', description: <><UndoOutlined style={{ color: '#16a34a', marginRight: 4 }} />可逆：可修改/删除/回退</> },
          { title: '会计复核确认', description: <><SafetyCertificateOutlined style={{ color: '#dc2626', marginRight: 4 }} />不可逆：确认后仅可红字冲销</> },
        ]}
      />

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        style={{ marginBottom: 16 }}
        items={[
          {
            key: 'docs',
            label: '① 原始凭证入库',
            children: (
              <>
                {mainContent}
                {!isClient && (
                  <div style={{ textAlign: 'center', marginTop: 16, marginBottom: 8 }}>
                    <Space direction="vertical" style={{ width: '100%' }}>
                      <Button icon={<RocketOutlined />} loading={processing} onClick={handleManualProcess}
                        style={{ color: '#2563eb', borderColor: '#2563eb' }}>
                        全自动加工（OCR→凭证→申报）
                      </Button>
                      {documents.length > 0 && (
                        <Button type="primary" icon={<ArrowDownOutlined />} onClick={() => setActiveTab('vouchers')}>
                          下一步：生成记账凭证
                        </Button>
                      )}
                    </Space>
                  </div>
                )}
              </>
            ),
          },
          {
            key: 'vouchers',
            label: '② 记账凭证生成',
            children: !isClient ? (
              <Card
                size="small"
                title={<span><Tag color="blue" style={{ marginRight: 8 }}>②</Tag>记账凭证生成</span>}
                style={{ marginBottom: 16 }}
              >
                {voucherLoading ? <Spin size="small" style={{ display: 'block', margin: '20px auto' }} /> : vouchers.length === 0 ? (
                  <EmptyState title="暂无记账凭证" description="上传原始凭证后，点击下方按钮生成" icon={<RobotOutlined style={{ fontSize: 48, color: '#d9d9d9' }} />} />
                ) : (
                  <Table
                    dataSource={vouchers}
                    rowKey="id"
                    size="small"
                    pagination={false}
                    columns={[
                      { title: '凭证编号', dataIndex: 'voucher_no', width: 120 },
                      { title: '日期', dataIndex: 'voucher_date', width: 100 },
                      { title: '摘要', dataIndex: 'summary', ellipsis: true },
                      { title: '借方', dataIndex: 'total_debit', width: 100, render: (v: number) => v ? `¥${v.toLocaleString()}` : '-' },
                      { title: '贷方', dataIndex: 'total_credit', width: 100, render: (v: number) => v ? `¥${v.toLocaleString()}` : '-' },
                      {
                        title: '状态', dataIndex: 'status', width: 80,
                        render: (s: string) => {
                          const m: Record<string, { color: string; text: string }> = { draft: { color: 'default', text: '草稿' }, pending_review: { color: 'orange', text: '待复核' }, confirmed: { color: 'green', text: '已确认' }, rejected: { color: 'red', text: '已驳回' }, reversed: { color: '#8b5cf6', text: '已冲销' } }
                          const i = m[s] || { color: 'default', text: s }
                          return <Tag color={i.color}>{i.text}</Tag>
                        },
                      },
                      {
                        title: '操作', width: 250,
                        render: (_: any, r: any) => (
                          <Space size={4} wrap>
                            <Button size="small" icon={<EyeOutlined />} onClick={() => { setSelectedVoucher(r); setVoucherDetailOpen(true) }}>详情</Button>
                            {r.status === 'pending_review' && (
                              <Button size="small" icon={<UndoOutlined />} style={{ color: '#d97706', borderColor: '#d97706' }} onClick={() => handleRollbackVoucher(r)}>回退</Button>
                            )}
                            {r.status !== 'confirmed' && r.status !== 'reversed' ? (
                              <>
                                <Button size="small" icon={<EditOutlined />} onClick={() => handleEditVoucher(r)}>修正</Button>
                                <Button size="small" danger icon={<DeleteOutlined />} onClick={() => handleDeleteVoucher(r)}>删除</Button>
                              </>
                            ) : r.status === 'confirmed' ? (
                              <Button size="small" danger onClick={() => handleReverseVoucher(r)}>红字冲销</Button>
                            ) : null}
                          </Space>
                        ),
                      },
                    ]}
                  />
                )}
                <div style={{ textAlign: 'center', marginTop: 12 }}>
                  <Space wrap>
                    <Button icon={<RobotOutlined />} onClick={() => {
                      const doneDocs = documents.filter(d => d.ocr_status === 'done')
                      if (doneDocs.length === 0) { message.warning('没有已 OCR 识别的原始凭证'); return }
                      setSelectedDocIds([])
                      setAiVoucherModalOpen(true)
                    }}>
                      AI 生成凭证
                    </Button>
                    <Button onClick={handleManualVoucher}>手工录入</Button>
                  </Space>
                </div>
                {vouchers.length > 0 && (
                  <div style={{ textAlign: 'center', marginTop: 12 }}>
                    <Space>
                      <Button icon={<ArrowUpOutlined />} onClick={() => setActiveTab('docs')}>
                        返回：原始凭证入库
                      </Button>
                      <Button type="primary" icon={<ArrowDownOutlined />} onClick={() => setActiveTab('review')}>
                        下一步：会计复核确认
                      </Button>
                    </Space>
                  </div>
                )}
              </Card>
            ) : null,
          },
          {
            key: 'review',
            label: '③ 会计复核确认',
            children: !isClient ? (
              <Card
                size="small"
                title={<span><Tag color="orange" style={{ marginRight: 8 }}>③</Tag>会计复核确认</span>}
                style={{ marginBottom: 16 }}
              >
                {vouchers.filter(v => v.status === 'pending_review' || v.status === 'draft').length === 0 ? (
                  <EmptyState title="暂无待复核凭证" description="生成记账凭证后将自动进入复核队列" icon={<CheckOutlined style={{ fontSize: 48, color: '#d9d9d9' }} />} />
                ) : (
                  <Table
                    dataSource={vouchers.filter(v => v.status === 'pending_review' || v.status === 'draft')}
                    rowKey="id"
                    size="small"
                    pagination={false}
                    columns={[
                      { title: '凭证编号', dataIndex: 'voucher_no', width: 120 },
                      { title: '摘要', dataIndex: 'summary', ellipsis: true },
                      { title: '借方', dataIndex: 'total_debit', width: 100, render: (v: number) => v ? `¥${v.toLocaleString()}` : '-' },
                      { title: '贷方', dataIndex: 'total_credit', width: 100, render: (v: number) => v ? `¥${v.toLocaleString()}` : '-' },
                      { title: '创建方式', dataIndex: 'created_by', width: 70, render: (b: string) => <Tag color={b === 'ai' ? 'purple' : 'default'}>{b === 'ai' ? 'AI' : '手工'}</Tag> },
                      {
                        title: '操作', width: 180,
                        render: (_: any, r: any) => (
                          <Space size={4} wrap>
                            <Button size="small" type="primary" icon={<CheckOutlined />} style={{ background: '#52c41a', borderColor: '#52c41a' }} loading={confirmLoading} onClick={() => handleReviewConfirm(r)}>复核通过</Button>
                            <Button size="small" danger icon={<CloseOutlined />} onClick={() => handleReviewReject(r)}>退回</Button>
                          </Space>
                        ),
                      },
                    ]}
                  />
                )}
                <div style={{ textAlign: 'center', marginTop: 12 }}>
                  <Input
                    size="small"
                    placeholder="审核人姓名（签章）"
                    value={reviewerName}
                    onChange={e => setReviewerName(e.target.value)}
                    style={{ width: 180 }}
                    prefix={<SafetyCertificateOutlined />}
                  />
                </div>
                {vouchers.some(v => v.status === 'confirmed') && (
                  <div style={{ textAlign: 'center', marginTop: 12 }}>
                    <Space>
                      <Button icon={<ArrowUpOutlined />} onClick={() => setActiveTab('vouchers')}>
                        返回：记账凭证生成
                      </Button>
                      <Button type="primary" icon={<ArrowDownOutlined />} onClick={() => navigate('/tax-filings')}>
                        下一步：前往报税
                      </Button>
                    </Space>
                  </div>
                )}
              </Card>
            ) : null,
          },
        ]}
      />


      {/* ===== AI 生成凭证弹窗 ===== */}
      <Modal
        title="AI 智能生成记账凭证"
        open={aiVoucherModalOpen}
        onOk={handleAIGenerateVoucher}
        onCancel={() => setAiVoucherModalOpen(false)}
        width={500}
        okText="生成凭证"
      >
        <div style={{ marginBottom: 12, color: '#64748b', fontSize: 13 }}>
          选择已 OCR 识别的原始凭证，AI 将自动分析票据内容并生成借贷分录。
        </div>
        <Select
          mode="multiple"
          style={{ width: '100%' }}
          placeholder="选择原始凭证"
          value={selectedDocIds}
          onChange={setSelectedDocIds}
          options={documents.filter(d => d.ocr_status === 'done').map((d: any) => ({
            label: `${d.file_name || d.id} (${d.doc_type})`,
            value: d.id,
          }))}
        />
      </Modal>

      {/* ===== 凭证详情弹窗 ===== */}
      <Modal
        title={`凭证详情 — ${selectedVoucher?.voucher_no || ''}`}
        open={voucherDetailOpen}
        onCancel={() => setVoucherDetailOpen(false)}
        footer={null}
        width={800}
      >
        {selectedVoucher && (
          <>
            <Descriptions bordered size="small" column={3} style={{ marginBottom: 12 }}>
              <Descriptions.Item label="编号">{selectedVoucher.voucher_no}</Descriptions.Item>
              <Descriptions.Item label="日期">{selectedVoucher.voucher_date}</Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag color={selectedVoucher.status === 'confirmed' ? 'green' : 'blue'}>{selectedVoucher.status}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="制单人">{selectedVoucher.maker || '-'}</Descriptions.Item>
              <Descriptions.Item label="审核人">{selectedVoucher.reviewer || '-'}</Descriptions.Item>
              <Descriptions.Item label="记账人">{selectedVoucher.bookkeeper || '-'}</Descriptions.Item>
              <Descriptions.Item label="借方合计">¥{selectedVoucher.total_debit?.toLocaleString()}</Descriptions.Item>
              <Descriptions.Item label="贷方合计">¥{selectedVoucher.total_credit?.toLocaleString()}</Descriptions.Item>
              <Descriptions.Item label="摘要" span={3}>{selectedVoucher.summary}</Descriptions.Item>
            </Descriptions>
            <Table
              dataSource={(selectedVoucher.entries || []).map((e: any, i: number) => ({ ...e, key: i }))}
              columns={[
                { title: '科目编码', dataIndex: 'account_code', width: 100 },
                { title: '科目名称', dataIndex: 'account_name', width: 120 },
                { title: '摘要', dataIndex: 'summary' },
                { title: '借方', dataIndex: 'debit', width: 100, render: (v: number) => v ? `¥${v.toLocaleString()}` : '-' },
                { title: '贷方', dataIndex: 'credit', width: 100, render: (v: number) => v ? `¥${v.toLocaleString()}` : '-' },
              ]}
              pagination={false}
              size="small"
            />
          </>
        )}
      </Modal>

      {/* ===== 凭证修正弹窗 ===== */}
      <Modal
        title={selectedVoucher ? `修正记账凭证 — ${selectedVoucher?.voucher_no || ''}` : '手工录入记账凭证'}
        open={voucherEditOpen}
        onOk={handleSaveVoucherEdit}
        onCancel={() => setVoucherEditOpen(false)}
        width={900}
        okText={selectedVoucher ? '保存修正' : '创建凭证'}
      >
        <Form form={voucherEditForm} layout="vertical">
          <Row gutter={16}>
            {!selectedVoucher && (
              <Col span={8}>
                <Form.Item label="凭证日期" name="voucher_date" rules={[{ required: true, message: '请选择日期' }]}>
                  <Input type="date" />
                </Form.Item>
              </Col>
            )}
          </Row>
          <Form.Item label="凭证摘要" name="summary" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.List name="entries">
            {(fields, { add, remove }) => (
              <>
                {fields.map(({ key, name, ...rest }) => (
                  <Row key={key} gutter={8} style={{ marginBottom: 8 }} align="middle">
                    <Col span={3}>
                      <Form.Item {...rest} name={[name, 'account_code']} noStyle>
                        <Input placeholder="科目编码" />
                      </Form.Item>
                    </Col>
                    <Col span={5}>
                      <Form.Item {...rest} name={[name, 'account_name']} noStyle>
                        <Input placeholder="科目名称" />
                      </Form.Item>
                    </Col>
                    <Col span={4}>
                      <Form.Item {...rest} name={[name, 'summary']} noStyle>
                        <Input placeholder="摘要" />
                      </Form.Item>
                    </Col>
                    <Col span={4}>
                      <Form.Item {...rest} name={[name, 'debit']} noStyle>
                        <InputNumber placeholder="借方" style={{ width: '100%' }} min={0} precision={2} />
                      </Form.Item>
                    </Col>
                    <Col span={4}>
                      <Form.Item {...rest} name={[name, 'credit']} noStyle>
                        <InputNumber placeholder="贷方" style={{ width: '100%' }} min={0} precision={2} />
                      </Form.Item>
                    </Col>
                    <Col span={3}>
                      <Button danger size="small" icon={<CloseOutlined />} onClick={() => remove(name)}>删除</Button>
                    </Col>
                  </Row>
                ))}
                <Button type="dashed" onClick={() => add({ account_code: '', account_name: '', summary: '', debit: 0, credit: 0 })} block>
                  + 添加分录行
                </Button>
              </>
            )}
          </Form.List>
        </Form>
      </Modal>

      {/* ===== 票据详情弹窗 ===== */}
      <Modal title="原始凭证详情" open={detailOpen} onCancel={() => setDetailOpen(false)} footer={null} width={700}>
        {selectedDoc && (
          <Descriptions bordered size="small" column={2}>
            <Descriptions.Item label="文件名">{selectedDoc.file_name}</Descriptions.Item>
            <Descriptions.Item label="类型">{selectedDoc.doc_type}</Descriptions.Item>
            <Descriptions.Item label="OCR状态">
              <Tag color={selectedDoc.ocr_status === 'done' ? 'green' : 'default'}>{selectedDoc.ocr_status}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="创建时间">{selectedDoc.created_at?.slice(0, 19)}</Descriptions.Item>
            {selectedDoc.ocr_structured && (
              <Descriptions.Item label="OCR数据" span={2}>
                <pre style={{ fontSize: 12, whiteSpace: 'pre-wrap' }}>{JSON.stringify(selectedDoc.ocr_structured, null, 2)}</pre>
              </Descriptions.Item>
            )}
          </Descriptions>
        )}
      </Modal>

      {/* ===== OCR 修正弹窗 ===== */}
      <Modal title="人工修正 OCR 识别结果" open={ocrEditOpen} onOk={handleOCRSave} onCancel={() => setOcrEditOpen(false)} width={600} okText="保存修正">
        <Form form={ocrForm} layout="vertical">
          <Space style={{ width: '100%' }} direction="vertical">
            <Form.Item label="发票代码" name="invoice_code"><Input /></Form.Item>
            <Form.Item label="发票号码" name="invoice_no"><Input /></Form.Item>
            <Form.Item label="开票日期" name="date"><Input placeholder="YYYY-MM-DD" /></Form.Item>
            <Form.Item label="销售方" name="seller_name"><Input /></Form.Item>
            <Form.Item label="购买方" name="buyer_name"><Input /></Form.Item>
            <Space size={12}>
              <Form.Item label="不含税金额" name="amount_excluding_tax"><InputNumber precision={2} /></Form.Item>
              <Form.Item label="税额" name="tax_amount"><InputNumber precision={2} /></Form.Item>
              <Form.Item label="总金额" name="total_amount"><InputNumber precision={2} /></Form.Item>
            </Space>
          </Space>
        </Form>
        <div style={{ color: '#2563eb', background: '#eff6ff', padding: 12, borderRadius: 6, marginTop: 8, fontSize: 13 }}>
          OCR 识别结果如有偏差，可在此修正。修正后将记录审计日志并支持追溯。
        </div>
      </Modal>

      {/* ===== 审计日志弹窗 ===== */}
      <Modal title="操作审计日志" open={auditOpen} onCancel={() => setAuditOpen(false)} footer={null} width={700}>
        <Table dataSource={auditTrail} columns={[
          { title: '时间', dataIndex: 'created_at', width: 180, render: (v: string) => v?.slice(0, 19) },
          { title: '操作', dataIndex: 'action', width: 100, render: (a: string) => <Tag color={a === 'corrected' ? 'orange' : 'blue'}>{a}</Tag> },
          { title: '操作人', dataIndex: 'operator', width: 100 },
          { title: '详情', dataIndex: 'detail', render: (d: any) => d ? JSON.stringify(d).substring(0, 200) : '-' },
        ]} rowKey="id" size="small" pagination={false} locale={{ emptyText: '暂无操作记录' }} />
      </Modal>

      {/* ===== 记账追溯 Drawer ===== */}
      <Drawer
        title={`记账追溯 — ${traceTarget}`}
        open={traceDrawerOpen}
        onClose={() => setTraceDrawerOpen(false)}
        width={480}
      >
        {traceLoading ? <Spin style={{ display: 'block', margin: '40px auto' }} /> :
         traceChain.length === 0 ? <Empty description="暂无追溯记录，该凭证尚未进入记账流程" /> : (
          <Timeline
            items={traceChain.map((item: any, i: number) => ({
              color: i === traceChain.length - 1 ? 'green' : 'blue',
              children: (
                <div>
                  <Tag color={i === traceChain.length - 1 ? 'green' : 'blue'}>{item.stage_name || item.stage}</Tag>
                  <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 4 }}>{item.created_at?.slice(0, 19)}</div>
                </div>
              ),
            }))}
          />
        )}
      </Drawer>

      {/* ===== 多渠道采集弹窗 ===== */}

      {/* 邮件采集 */}
      <Modal
        title={<Space><MailOutlined style={{ color: '#7c3aed' }} />邮件采集</Space>}
        open={channelModal === 'email'}
        onOk={handleEmailCollect}
        onCancel={() => { setChannelModal(null); setChannelResult(null) }}
        confirmLoading={channelLoading}
        okText="立即采集"
        width={520}
      >
        <div style={{ marginBottom: 16, padding: '12px 16px', background: '#f5f3ff', borderRadius: 6, border: '1px solid #ddd6fe', fontSize: 13 }}>
          <Text strong style={{ color: '#7c3aed' }}>采集邮箱地址</Text>
          <div style={{ marginTop: 8, padding: '8px 12px', background: '#fff', borderRadius: 4, fontFamily: 'monospace', fontSize: 14 }}>
            collect+{currentClientId || 'default'}@zhangyaoyao.com
          </div>
          <div style={{ marginTop: 8, color: '#64748b', fontSize: 12 }}>
            将发票、收据等电子凭证以附件形式发送至上述邮箱，系统将自动解析并入库。支持 PDF、JPG、PNG 格式。
          </div>
        </div>
        {channelResult && channelResult.channel === 'email' && (
          <Result status="success" title="邮件采集完成" subTitle={channelResult.message}
            extra={<Button onClick={() => setChannelModal(null)}>关闭</Button>} />
        )}
      </Modal>

      {/* 电子税务局拉取 */}
      <Modal
        title={<Space><CloudDownloadOutlined style={{ color: '#dc2626' }} />电子税务局拉取</Space>}
        open={channelModal === 'tax_pull'}
        onOk={handleTaxPull}
        onCancel={() => { setChannelModal(null); setChannelResult(null) }}
        confirmLoading={channelLoading}
        okText="开始拉取"
        width={520}
      >
        <div style={{ marginBottom: 16, padding: '12px 16px', background: '#fef2f2', borderRadius: 6, border: '1px solid #fecaca', fontSize: 13 }}>
          <Text strong style={{ color: '#dc2626' }}>自动拉取进项发票</Text>
          <div style={{ marginTop: 8, color: '#64748b', fontSize: 12 }}>
            通过 Playwright 自动登录电子税务局，拉取所选期间的进项发票数据。拉取过程需要 30-60 秒，请耐心等待。
          </div>
          <div style={{ marginTop: 8, color: '#94a3b8', fontSize: 11 }}>
            拉取范围：当月进项发票 · 增值税专用发票 + 普通发票
          </div>
        </div>
        {channelResult && channelResult.channel === 'tax_pull' && (
          <Result status="success" title="拉取完成" subTitle={channelResult.message}
            extra={<Button onClick={() => setChannelModal(null)}>关闭</Button>} />
        )}
      </Modal>

      {/* 扫码采集 */}
      <Modal
        title={<Space><ScanOutlined style={{ color: '#16a34a' }} />扫码采集</Space>}
        open={channelModal === 'qr_scan'}
        onCancel={() => setChannelModal(null)}
        footer={<Button onClick={() => setChannelModal(null)}>关闭</Button>}
        width={420}
      >
        <div style={{ textAlign: 'center', padding: '20px 0' }}>
          <div style={{ width: 160, height: 160, margin: '0 auto 16px', background: '#f1f5f9', borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', border: '2px dashed #cbd5e1' }}>
            <QrcodeOutlined style={{ fontSize: 80, color: '#16a34a' }} />
          </div>
          <Text strong style={{ fontSize: 14 }}>手机扫码上传票据</Text>
          <div style={{ marginTop: 8, fontSize: 12, color: '#64748b' }}>
            使用手机扫描二维码，在移动端拍照或选择文件上传票据。<br />
            二维码有效期：24 小时
          </div>
          <div style={{ marginTop: 12, padding: '8px 12px', background: '#f0fdf4', borderRadius: 4, fontFamily: 'monospace', fontSize: 11, color: '#16a34a', wordBreak: 'break-all' }}>
            {window.location.origin}/upload?client_id={currentClientId || ''}
          </div>
          <Button type="link" size="small" style={{ marginTop: 8 }}
            onClick={() => {
              navigator.clipboard.writeText(`${window.location.origin}/upload?client_id=${currentClientId || ''}`).then(() => message.success('链接已复制')).catch(() => message.error('复制失败'))
            }}>
            复制采集链接
          </Button>
        </div>
      </Modal>

      {/* ZIP 导入 */}
      <Modal
        title={<Space><FileZipOutlined style={{ color: '#d97706' }} />ZIP 批量导入</Space>}
        open={channelModal === 'zip'}
        onCancel={() => { setChannelModal(null); setChannelResult(null) }}
        footer={null}
        width={480}
      >
        <div style={{ marginBottom: 16, padding: '12px 16px', background: '#fffbeb', borderRadius: 6, border: '1px solid #fde68a', fontSize: 13 }}>
          <Text strong style={{ color: '#d97706' }}>批量上传发票压缩包</Text>
          <div style={{ marginTop: 8, color: '#64748b', fontSize: 12 }}>
            上传 ZIP 压缩包，系统自动解压、分类并逐张入库生成原始凭证。支持包含发票、回单、合同的混合压缩包，最大 100MB。
          </div>
        </div>
        <div style={{ textAlign: 'center', padding: '20px 0' }}>
          <Upload
            accept=".zip"
            showUploadList={false}
            beforeUpload={async (file) => {
              if (!currentClientId) { message.warning('请先选择客户'); return false }
              setChannelLoading(true)
              try {
                const formData = new FormData()
                formData.append('file', file)
                formData.append('client_id', currentClientId)
                const res: any = await automationApi.zipImport(formData)
                setChannelResult({ ...res, channel: 'zip' })
                message.success(res.message || '导入完成')
                fetchDocuments()
              } catch { message.error('导入失败') }
              setChannelLoading(false)
              return false
            }}
          >
            <Button type="primary" icon={<UploadOutlined />} loading={channelLoading} size="large">
              选择 ZIP 文件
            </Button>
          </Upload>
        </div>
        {channelResult && channelResult.channel === 'zip' && (
          <Result status="success" title="导入完成"
            subTitle={`成功 ${channelResult.imported || 0} 张，跳过 ${channelResult.skipped || 0} 张`}
            extra={<Button onClick={() => setChannelModal(null)}>关闭</Button>} />
        )}
      </Modal>

      {/* 微信/钉钉 Webhook */}
      <Modal
        title={<Space><RobotOutlined style={{ color: '#0891b2' }} />微信/钉钉机器人采集</Space>}
        open={channelModal === 'webhook'}
        onCancel={() => { setChannelModal(null); setChannelResult(null) }}
        footer={null}
        width={520}
      >
        <div style={{ marginBottom: 16 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            配置企业微信或钉钉机器人 Webhook，群聊中的票据文件自动推送到本系统。
          </Text>
        </div>

        {/* 已有 webhooks */}
        {webhooks.length > 0 && (
          <div style={{ marginBottom: 16 }}>
            <Text strong style={{ fontSize: 13 }}>已配置的机器人</Text>
            {webhooks.map((wh: any) => (
              <div key={wh.id} style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                padding: '8px 12px', marginTop: 8, background: '#f8fafc', borderRadius: 6,
                border: '1px solid #e2e8f0',
              }}>
                <div>
                  <Tag color={wh.platform === 'wechat' ? 'green' : 'blue'}>
                    {wh.platform === 'wechat' ? '微信' : '钉钉'}
                  </Tag>
                  <Text style={{ fontSize: 12, fontFamily: 'monospace' }}>/api/webhook/{wh.platform}?token={wh.token?.substring(0, 8)}...</Text>
                </div>
                <Space>
                  <Button size="small" type={wh.enabled ? 'primary' : 'default'}
                    onClick={() => handleToggleWebhook(wh.id, !wh.enabled)}>
                    {wh.enabled ? '已启用' : '已停用'}
                  </Button>
                  <Button size="small" danger onClick={() => handleRemoveWebhook(wh.id)}>移除</Button>
                </Space>
              </div>
            ))}
          </div>
        )}

        {/* 新建 webhook */}
        <div style={{ padding: '12px', background: '#f0fdfa', borderRadius: 6, border: '1px solid #ccfbf1' }}>
          <Text strong style={{ fontSize: 13 }}>新建机器人</Text>
          <div style={{ marginTop: 8, display: 'flex', gap: 8 }}>
            <Select value={webhookPlatform} onChange={setWebhookPlatform} style={{ width: 100 }}>
              <Select.Option value="wechat">企业微信</Select.Option>
              <Select.Option value="dingtalk">钉钉</Select.Option>
            </Select>
            <Button type="primary" loading={webhookCreating} onClick={handleAddWebhook}
              style={{ background: '#0891b2', borderColor: '#0891b2' }}>
              创建机器人
            </Button>
          </div>
          <div style={{ marginTop: 8, fontSize: 11, color: '#64748b' }}>
            创建后将获得 Webhook URL，在{webhookPlatform === 'wechat' ? '企业微信' : '钉钉'}机器人管理后台配置即可。
          </div>
        </div>

        {channelResult && channelResult.channel === 'webhook' && (
          <Result status="success" title="配置完成" subTitle={channelResult.message}
            extra={<Button onClick={() => setChannelModal(null)}>关闭</Button>} />
        )}
      </Modal>

    </div>
  )
}
