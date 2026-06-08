import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, Table, Tag, Space, Button, Badge, Modal, Form, Select, Input, App, Descriptions, Steps, Result, Typography, Divider, Statistic, Row, Col, Spin } from 'antd'
import {
  PlusOutlined, AuditOutlined, FileSearchOutlined, DeleteOutlined,
  CalculatorOutlined, CheckCircleOutlined, DollarOutlined, SendOutlined, InboxOutlined,
} from '@ant-design/icons'
import { filingApi, feedbackApi, taxAutoApi } from '@/services/api'
import { useClient } from '@/contexts/ClientContext'
import SkeletonTable from '@/components/SkeletonTable'
import EmptyState from '@/components/EmptyState'

const { Text, Title } = Typography

const TAX_TYPE_MAP: Record<string, string> = {
  vat: '增值税', corporate_income: '企业所得税', individual_income: '个人所得税', stamp_duty: '印花税', surtax: '附加税',
}

export default function TaxFilings() {
  const [filings, setFilings] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [previewOpen, setPreviewOpen] = useState(false)
  const [previewData, setPreviewData] = useState<any>(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [detailOpen, setDetailOpen] = useState(false)
  const [reviewOpen, setReviewOpen] = useState(false)
  const [auditOpen, setAuditOpen] = useState(false)
  const [selected, setSelected] = useState<any>(null)
  const [auditTrail, setAuditTrail] = useState<any[]>([])
  const [step, setStep] = useState(0)
  const [createForm] = Form.useForm()
  const [reviewForm] = Form.useForm()
  const navigate = useNavigate()
  const { currentClientId } = useClient()
  const { message } = App.useApp()

  const fetchFilings = async () => {
    setLoading(true)
    try {
      const res: any = await filingApi.list({ page: 1, page_size: 50, client_id: currentClientId })
      setFilings(res.items || [])
    } catch { message.error('加载申报记录失败') }
    setLoading(false)
  }

  useEffect(() => { fetchFilings() }, [currentClientId])

  // Step 1: Preview tax data before creating
  const handlePreview = async () => {
    const values = await createForm.validateFields()
    setPreviewLoading(true)
    try {
      const res: any = await filingApi.preview({
        tax_type: values.tax_type,
        period: values.period,
        taxpayer_type: values.taxpayer_type || 'small',
      })
      setPreviewData(res)
      setStep(1)
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '预览失败，请确认有已确认的凭证')
    }
    setPreviewLoading(false)
  }

  // Step 2: Confirm and create
  const handleCreate = async () => {
    const values = createForm.getFieldsValue()
    try {
      const idempotencyKey = crypto.randomUUID()
      await filingApi.create({ ...values, client_id: currentClientId, idempotency_key: idempotencyKey })
      message.success('申报任务已创建，数据已自动预填')
      setCreateOpen(false)
      setStep(0)
      createForm.resetFields()
      setPreviewData(null)
      fetchFilings()
    } catch { message.error('创建失败') }
  }

  const handleReview = async () => {
    const values = await reviewForm.validateFields()
    try {
      await feedbackApi.reviewFiling(selected.id, values)
      message.success('审核完成')
      setReviewOpen(false)
      reviewForm.resetFields()
      fetchFilings()
    } catch { message.error('审核失败') }
  }

  const handleAutoFile = async (record: any) => {
    Modal.confirm({
      title: '自动申报',
      content: (
        <div>
          <p>将使用 <strong>Playwright 引擎</strong> 自动登录电子税务局并提交申报。</p>
          <p>请确认已在系统设置中配置电子税务局登录凭据。</p>
          <p style={{ color: '#fa8c16' }}>⚠️ 建议先在 headless=false 模式下测试。</p>
        </div>
      ),
      okText: '开始自动申报',
      onOk: async () => {
        try {
          const res: any = await taxAutoApi.file(record.id, 'generic')
          if (res.success) {
            message.success(`申报成功！流水号: ${res.transaction_id}`)
          } else {
            message.warning(res.message)
          }
          fetchFilings()
        } catch (e: any) {
          message.error(e?.response?.data?.detail || '自动申报失败')
        }
      },
    })
  }

  const showAudit = async (record: any) => {
    setSelected(record)
    try {
      const res: any = await feedbackApi.auditTrail('filing', record.id)
      setAuditTrail(res.items || res || [])
    } catch { setAuditTrail([]) }
    setAuditOpen(true)
  }

  const renderTaxPreview = () => {
    if (!previewData) return null
    const d = previewData
    const taxType = d.tax_type

    if (taxType === 'vat' || taxType === 'vat_small') {
      return (
        <Descriptions bordered size="small" column={2} style={{ marginTop: 16 }}>
          <Descriptions.Item label="税种">
            <Tag color="blue">{taxType === 'vat_small' ? '增值税（小规模纳税人）' : '增值税（一般纳税人）'}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="所属期">{d.period}</Descriptions.Item>
          <Descriptions.Item label="本期销售额">
            <Text strong>¥{(d.period_sales || 0).toLocaleString()}</Text>
          </Descriptions.Item>
          <Descriptions.Item label="税率">{(d.tax_rate * 100).toFixed(1)}%</Descriptions.Item>
          {taxType !== 'vat_small' && (
            <>
              <Descriptions.Item label="销项税额">¥{(d.period_output_tax || 0).toLocaleString()}</Descriptions.Item>
              <Descriptions.Item label="进项税额">¥{(d.period_input_tax || 0).toLocaleString()}</Descriptions.Item>
            </>
          )}
          <Descriptions.Item label="应纳税额" span={2}>
            <Text strong style={{ fontSize: 20, color: '#1677ff' }}>
              ¥{(d.tax_payable || 0).toLocaleString()}
            </Text>
          </Descriptions.Item>
          {d.tax_reduction > 0 && (
            <Descriptions.Item label="减免税额" span={2}>
              <Text type="success">¥{d.tax_reduction.toLocaleString()}（小规模纳税人月销售额≤10万免征）</Text>
            </Descriptions.Item>
          )}
        </Descriptions>
      )
    }

    if (taxType === 'corporate_income') {
      return (
        <Descriptions bordered size="small" column={2} style={{ marginTop: 16 }}>
          <Descriptions.Item label="税种"><Tag color="purple">企业所得税</Tag></Descriptions.Item>
          <Descriptions.Item label="所属期">{d.period}</Descriptions.Item>
          <Descriptions.Item label="累计收入">¥{(d.cumulative_income || 0).toLocaleString()}</Descriptions.Item>
          <Descriptions.Item label="累计成本">¥{(d.cumulative_cost || 0).toLocaleString()}</Descriptions.Item>
          <Descriptions.Item label="累计利润">
            <Text type={d.cumulative_profit >= 0 ? 'success' : 'danger'}>
              ¥{(d.cumulative_profit || 0).toLocaleString()}
            </Text>
          </Descriptions.Item>
          <Descriptions.Item label="税率">25%</Descriptions.Item>
          <Descriptions.Item label="应纳税所得额">¥{Math.max(0, d.cumulative_profit || 0).toLocaleString()}</Descriptions.Item>
          <Descriptions.Item label="已预缴税额">¥{(d.prepaid_tax || 0).toLocaleString()}</Descriptions.Item>
          <Descriptions.Item label="本期应补(退)税额" span={2}>
            <Text strong style={{ fontSize: 20, color: '#1677ff' }}>
              ¥{(d.actual_payable || 0).toLocaleString()}
            </Text>
          </Descriptions.Item>
        </Descriptions>
      )
    }

    if (taxType === 'surtax') {
      return (
        <Descriptions bordered size="small" column={2} style={{ marginTop: 16 }}>
          <Descriptions.Item label="税种"><Tag color="cyan">附加税</Tag></Descriptions.Item>
          <Descriptions.Item label="所属期">{d.period}</Descriptions.Item>
          <Descriptions.Item label="增值税基数">¥{(d.base_vat || 0).toLocaleString()}</Descriptions.Item>
          <Descriptions.Item label="城建税(7%)">¥{(d.urban_construction || 0).toLocaleString()}</Descriptions.Item>
          <Descriptions.Item label="教育费附加(3%)">¥{(d.education_surcharge || 0).toLocaleString()}</Descriptions.Item>
          <Descriptions.Item label="地方教育附加(2%)">¥{(d.local_education_surcharge || 0).toLocaleString()}</Descriptions.Item>
          <Descriptions.Item label="附加税合计" span={2}>
            <Text strong style={{ fontSize: 20, color: '#1677ff' }}>
              ¥{(d.total_surtax || 0).toLocaleString()}
            </Text>
          </Descriptions.Item>
        </Descriptions>
      )
    }

    return <pre style={{ fontSize: 12 }}>{JSON.stringify(d, null, 2)}</pre>
  }

  const renderFilingResult = (filingResult: any) => {
    if (!filingResult) return <Text type="secondary">暂无申报数据</Text>
    const d = filingResult
    if (d.tax_type === 'vat' || d.tax_type === 'vat_small') {
      return (
        <Descriptions size="small" column={2}>
          <Descriptions.Item label="销售额">¥{(d.period_sales || 0).toLocaleString()}</Descriptions.Item>
          <Descriptions.Item label="应纳税额">¥{(d.tax_payable || 0).toLocaleString()}</Descriptions.Item>
          {d.tax_reduction > 0 && <Descriptions.Item label="减免">¥{d.tax_reduction.toLocaleString()}</Descriptions.Item>}
        </Descriptions>
      )
    }
    if (d.tax_type === 'corporate_income') {
      return (
        <Descriptions size="small" column={2}>
          <Descriptions.Item label="利润">¥{(d.cumulative_profit || 0).toLocaleString()}</Descriptions.Item>
          <Descriptions.Item label="应纳税额">¥{(d.actual_payable || 0).toLocaleString()}</Descriptions.Item>
        </Descriptions>
      )
    }
    return <pre style={{ fontSize: 11, maxHeight: 150, overflow: 'auto' }}>{JSON.stringify(d, null, 2)}</pre>
  }

  const columns = [
    {
      title: '税种', dataIndex: 'tax_type', key: 'tax_type', width: 120,
      render: (t: string) => <Tag color="blue">{TAX_TYPE_MAP[t] || t}</Tag>,
    },
    { title: '所属期', dataIndex: 'period', key: 'period', width: 100 },
    {
      title: '申报数据', dataIndex: 'filing_result', key: 'filing_result', width: 300,
      render: (f: any) => renderFilingResult(f),
    },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 100,
      render: (s: string) => {
        const map: Record<string, { status: 'success' | 'processing' | 'default' | 'error'; text: string }> = {
          pending: { status: 'default', text: '待处理' },
          pending_review: { status: 'processing', text: '待审核' },
          submitted: { status: 'processing', text: '已提交' },
          success: { status: 'success', text: '申报成功' },
          failed: { status: 'error', text: '失败' },
        }
        const m = map[s] || { status: 'default' as const, text: s }
        return <Badge status={m.status} text={m.text} />
      },
    },
    { title: '审核人', dataIndex: 'reviewer', key: 'reviewer', width: 80, render: (v: string) => v || '-' },
    { title: '申报时间', dataIndex: 'filed_at', key: 'filed_at', width: 160, render: (v: string) => v ? v.slice(0, 19) : '-' },
    {
      title: '操作', key: 'actions', width: 220,
      render: (_: any, record: any) => (
        <Space>
          <Button type="link" size="small" icon={<FileSearchOutlined />}
            onClick={() => { setSelected(record); setDetailOpen(true) }}>详情</Button>
          {(record.status === 'pending' || record.status === 'pending_review') && (
            <>
              <Button type="link" size="small" icon={<AuditOutlined />}
                onClick={() => { setSelected(record); reviewForm.setFieldsValue({ action: 'approve' }); setReviewOpen(true) }}>审核</Button>
              <Button type="link" size="small" icon={<SendOutlined />} style={{ color: '#52c41a' }}
                onClick={() => handleAutoFile(record)}>自动申报</Button>
            </>
          )}
          <Button type="link" size="small" onClick={() => showAudit(record)}>日志</Button>
          <Button type="link" size="small" danger icon={<DeleteOutlined />}
            onClick={() => {
              Modal.confirm({
                title: '确认删除',
                content: `将删除申报记录: ${TAX_TYPE_MAP[record.tax_type] || record.tax_type} ${record.period}`,
                onOk: async () => {
                  try { await filingApi.delete(record.id); message.success('已删除'); fetchFilings() }
                  catch { message.error('删除失败') }
                },
              })
            }} />
        </Space>
      ),
    },
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 24 }}>
        <h2>纳税申报</h2>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => { setStep(0); setPreviewData(null); createForm.resetFields(); setCreateOpen(true) }}>
          创建申报
        </Button>
      </div>

      {loading ? (
        <SkeletonTable rows={5} columns={6} />
      ) : filings.length === 0 ? (
        <Card>
          <EmptyState
            title="暂无申报记录"
            description="通过票据中心完成自动加工后，申报任务将自动创建"
            actionLabel="前往票据中心"
            onAction={() => navigate('/documents')}
            icon={<InboxOutlined style={{ fontSize: 64, color: '#d9d9d9' }} />}
          />
        </Card>
      ) : (
        <Card style={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
          <Table dataSource={filings} columns={columns} rowKey="id" scroll={{ x: 1000 }} />
        </Card>
      )}

      {/* Create Filing Modal with Preview */}
      <Modal
        title={step === 0 ? '创建纳税申报' : '确认申报数据'}
        open={createOpen}
        onCancel={() => { setCreateOpen(false); setStep(0); setPreviewData(null) }}
        footer={step === 0 ? [
          <Button key="cancel" onClick={() => { setCreateOpen(false); setStep(0) }}>取消</Button>,
          <Button key="preview" type="primary" icon={<CalculatorOutlined />} loading={previewLoading} onClick={handlePreview}>
            预览申报数据
          </Button>,
        ] : [
          <Button key="back" onClick={() => setStep(0)}>上一步</Button>,
          <Button key="create" type="primary" icon={<CheckCircleOutlined />} onClick={handleCreate}>
            确认创建
          </Button>,
        ]}
        width={700}
      >
        {step === 0 ? (
          <Form form={createForm} layout="vertical">
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item label="税种" name="tax_type" rules={[{ required: true }]}>
                  <Select options={[
                    { label: '增值税', value: 'vat' },
                    { label: '企业所得税', value: 'corporate_income' },
                    { label: '附加税', value: 'surtax' },
                  ]} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item label="所属期" name="period" rules={[{ required: true }]} tooltip="格式：YYYY-MM">
                  <Input placeholder="2026-06" />
                </Form.Item>
              </Col>
            </Row>
            <Form.Item label="纳税人类型" name="taxpayer_type" tooltip="增值税适用" initialValue="small">
              <Select options={[
                { label: '小规模纳税人', value: 'small' },
                { label: '一般纳税人', value: 'general' },
              ]} />
            </Form.Item>
            <Divider />
            <Text type="secondary">
              <CalculatorOutlined /> 创建时将自动从已确认的记账凭证汇总计算申报数据，包括销售额、进销项税额、应纳税额等。
            </Text>
          </Form>
        ) : (
          <Spin spinning={previewLoading}>
            {previewData ? renderTaxPreview() : (
              <Result status="warning" title="无法计算" subTitle="未找到符合条件的已确认凭证" />
            )}
          </Spin>
        )}
      </Modal>

      {/* Detail Modal */}
      <Modal title="申报详情" open={detailOpen} onCancel={() => setDetailOpen(false)} footer={null} width={700}>
        {selected && (
          <>
            <Descriptions bordered size="small" column={2} style={{ marginBottom: 16 }}>
              <Descriptions.Item label="税种">{TAX_TYPE_MAP[selected.tax_type] || selected.tax_type}</Descriptions.Item>
              <Descriptions.Item label="所属期">{selected.period}</Descriptions.Item>
              <Descriptions.Item label="状态">
                <Badge status={selected.status === 'success' ? 'success' : 'processing'} text={selected.status} />
              </Descriptions.Item>
              <Descriptions.Item label="审核人">{selected.reviewer || '-'}</Descriptions.Item>
              <Descriptions.Item label="申报时间">{selected.filed_at ? selected.filed_at.slice(0, 19) : '-'}</Descriptions.Item>
              <Descriptions.Item label="RPA任务">{selected.rpa_task_id?.slice(0, 8) || '-'}</Descriptions.Item>
            </Descriptions>
            <Title level={5}>申报数据</Title>
            {renderFilingResult(selected.filing_result)}
          </>
        )}
      </Modal>

      {/* Review Modal */}
      <Modal title="审核申报" open={reviewOpen} onOk={handleReview} onCancel={() => setReviewOpen(false)} okText="提交审核">
        <Form form={reviewForm} layout="vertical">
          <Form.Item label="操作" name="action" rules={[{ required: true }]}>
            <Select options={[
              { label: '通过', value: 'approve' },
              { label: '驳回', value: 'reject' },
            ]} />
          </Form.Item>
          <Form.Item label="审核人" name="reviewer" rules={[{ required: true }]}>
            <Input placeholder="审核人姓名" />
          </Form.Item>
          <Form.Item label="审核意见" name="comment">
            <Input.TextArea rows={3} placeholder="审核意见" />
          </Form.Item>
        </Form>
      </Modal>

      {/* Audit Trail Modal */}
      <Modal title="操作日志" open={auditOpen} onCancel={() => setAuditOpen(false)} footer={null} width={700}>
        <Table dataSource={auditTrail} rowKey="id" size="small" pagination={false}
          columns={[
            { title: '时间', dataIndex: 'created_at', width: 170, render: (v: string) => v?.slice(0, 19) },
            { title: '操作', dataIndex: 'action', width: 100 },
            { title: '操作人', dataIndex: 'operator', width: 100 },
            { title: '详情', dataIndex: 'detail', render: (d: any) => typeof d === 'string' ? d : JSON.stringify(d) },
          ]}
        />
      </Modal>
    </div>
  )
}
