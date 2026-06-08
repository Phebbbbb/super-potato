import { useState, useEffect, useRef } from 'react'
import { Card, Upload, Table, Button, Space, Tag, Modal, Image, Input, Form, InputNumber, App, Descriptions, Typography, Progress, Steps, Result, Tooltip, Skeleton } from 'antd'
import { InboxOutlined, QrcodeOutlined, DeleteOutlined, EyeOutlined, EditOutlined, HistoryOutlined, RocketOutlined, CheckCircleOutlined, WarningOutlined, CloseCircleOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { useNavigate } from 'react-router-dom'
import { documentApi, feedbackApi, rpaApi } from '@/services/api'
import { useClient } from '@/contexts/ClientContext'
import EmptyState from '@/components/EmptyState'
import SkeletonTable from '@/components/SkeletonTable'

const { Dragger } = Upload
const { Text } = Typography

export default function Documents() {
  const [documents, setDocuments] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [detailOpen, setDetailOpen] = useState(false)
  const [ocrEditOpen, setOcrEditOpen] = useState(false)
  const [auditOpen, setAuditOpen] = useState(false)
  const [selectedDoc, setSelectedDoc] = useState<any>(null)
  const [auditTrail, setAuditTrail] = useState<any[]>([])
  const [ocrForm] = Form.useForm()
  const { currentClientId } = useClient()
  const navigate = useNavigate()
  const { message, modal } = App.useApp()

  // 上传批次追踪
  const [uploading, setUploading] = useState(false)
  const [uploadCount, setUploadCount] = useState(0)
  const uploadBatchRef = useRef<string[]>([])

  // 自动加工状态
  const [processing, setProcessing] = useState(false)
  const [processResult, setProcessResult] = useState<any>(null)

  const fetchDocuments = async () => {
    setLoading(true)
    try {
      const res: any = await documentApi.list({ page: 1, page_size: 50, client_id: currentClientId })
      setDocuments(res.items || [])
    } catch { message.error('加载原始凭证失败') }
    setLoading(false)
  }

  useEffect(() => { fetchDocuments() }, [currentClientId])

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
      // 从批次中移除
      uploadBatchRef.current = uploadBatchRef.current.filter(n => n !== name)
      setUploadCount(uploadBatchRef.current.length)

      // 全部完成
      if (uploadBatchRef.current.length === 0) {
        setUploading(false)
        fetchDocuments()

        if (info.file.status === 'done') {
          message.success(`${info.file.name} 上传成功并 OCR 识别完成`)
        }

        // 延迟一下等 OCR 完成，然后自动触发全自动加工
        setTimeout(() => {
          modal.confirm({
            title: '上传完成 — 是否立即自动处理？',
            icon: <RocketOutlined />,
            content: (
              <div style={{ fontSize: 13 }}>
                <p>系统将自动执行以下步骤：</p>
                <Steps
                  size="small"
                  direction="vertical"
                  current={-1}
                  style={{ marginTop: 12 }}
                  items={[
                    { title: 'OCR 票据识别', description: '自动提取发票金额、买卖方、税率等信息' },
                    { title: 'AI 智能生成记账凭证', description: '自动匹配科目、生成借贷分录、校验平衡' },
                    { title: '自动确认高置信度凭证', description: '分录≤3行且匹配标准科目 → 自动确认' },
                    { title: '自动创建纳税申报', description: '汇总凭证数据生成申报表，等待您审核提交' },
                  ]}
                />
              </div>
            ),
            okText: '开始自动处理',
            cancelText: '稍后手动处理',
            onOk: async () => {
              setProcessing(true)
              try {
                const res: any = await rpaApi.autoProcess(currentClientId || '')
                setProcessResult(res)
              } catch (e: any) {
                message.error(e?.response?.data?.detail || '自动加工失败')
                setProcessing(false)
              }
            },
          })
        }, 1500)
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

  // 手动触发全自动加工
  const handleManualProcess = async () => {
    if (!currentClientId) { message.warning('请先选择客户'); return }
    setProcessing(true)
    setProcessResult(null)
    try {
      const res: any = await rpaApi.autoProcess(currentClientId)
      setProcessResult(res)
      fetchDocuments()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '自动加工失败')
    }
    setProcessing(false)
  }

  // 一键申报提交
  const [submitting, setSubmitting] = useState(false)
  const [submitResult, setSubmitResult] = useState<any>(null)
  const handleAutoSubmit = async () => {
    if (!currentClientId) return
    setSubmitting(true)
    try {
      const res: any = await rpaApi.autoSubmitFilings(currentClientId)
      setSubmitResult(res)
      message.success(res.message)
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.detail || '申报提交失败，请检查电子税务局凭据配置')
    }
    setSubmitting(false)
  }

  // 跳转到报税中心
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

  const handleDelete = async (record: any) => {
    Modal.confirm({
      title: '确认删除',
      content: `确定要删除 "${record.file_name}" 吗？`,
      onOk: async () => {
        try { await documentApi.delete(record.id); message.success('已删除'); fetchDocuments() }
        catch (e: any) { message.error('删除失败') }
      },
    })
  }

  const columns: ColumnsType<any> = [
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
      title: '操作', key: 'actions', width: 220,
      render: (_: any, record: any) => (
        <Space size={0} wrap>
          <Button type="link" size="small" icon={<EyeOutlined />} onClick={() => showDetail(record)}>详情</Button>
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => handleOCREdit(record)}>修正</Button>
          <Button type="link" size="small" icon={<HistoryOutlined />} onClick={() => showAudit(record)}>日志</Button>
          <Button type="link" size="small" icon={<QrcodeOutlined />} onClick={() => navigate(`/trace?q=${record.id}`)}>QR</Button>
          <Button type="link" size="small" danger icon={<DeleteOutlined />} onClick={() => handleDelete(record)}>删除</Button>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <h2 style={{ margin: 0 }}>票据中心</h2>
        <Button
          icon={<RocketOutlined />}
          loading={processing}
          onClick={handleManualProcess}
          style={{ color: '#2563eb', borderColor: '#2563eb' }}
        >
          全自动加工（OCR→凭证→申报）
        </Button>
      </div>

      {/* 上传区 */}
      <Card style={{ marginBottom: 24 }}>
        <Dragger {...uploadProps} disabled={uploading}>
          <p className="ant-upload-drag-icon"><InboxOutlined /></p>
          <p className="ant-upload-text" style={{ fontSize: 16 }}>
            {uploading ? `正在上传 ${uploadCount} 个文件...` : '点击或拖拽文件/文件夹到此区域'}
          </p>
          <p className="ant-upload-hint">
            支持 JPG/PNG/PDF 批量上传 · 上传后自动 OCR 识别 · 完成自动触发全流程加工
          </p>
        </Dragger>
      </Card>

      {/* 自动处理结果 */}
      {processResult && (
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
          {/* 提交结果 */}
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
      {loading ? (
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
        <Card title={`票据列表 (${documents.length})`} style={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
          <Table
            dataSource={documents}
            columns={columns}
            rowKey="id"
            size="middle"
            locale={{ emptyText: '暂无票据' }}
            scroll={{ x: 900 }}
          />
        </Card>
      )}

      {/* ===== 详情弹窗 ===== */}
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
    </div>
  )
}
