import { useState, useEffect } from 'react'
import { Card, Table, Button, Space, Tag, Modal, Form, Input, Select, InputNumber, App, Typography, Result, Row, Col, Divider, Spin, Descriptions, Alert, Progress, Badge, Popconfirm } from 'antd'
import { PlusOutlined, SendOutlined, EyeOutlined, DeleteOutlined, CheckCircleOutlined, RocketOutlined, InboxOutlined, ThunderboltOutlined, RobotOutlined, SafetyCertificateOutlined, WarningOutlined, CloseCircleOutlined } from '@ant-design/icons'
import { invoiceApi, rpaApi, verifyApi } from '@/services/api'
import { useClient } from '@/contexts/ClientContext'
import { useRole } from '@/hooks/useRole'
import SkeletonTable from '@/components/SkeletonTable'
import EmptyState from '@/components/EmptyState'
import type { ColumnsType } from 'antd/es/table'

const { Text, Title } = Typography
const { TextArea } = Input

const RISK_COLORS: Record<string, string> = { low: '#16a34a', medium: '#d97706', high: '#dc2626', critical: '#7c3aed' }
const RISK_LABELS: Record<string, string> = { low: '低风险', medium: '中风险', high: '高风险', critical: '严重风险' }

export default function Invoicing() {
  const [invoices, setInvoices] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [detailOpen, setDetailOpen] = useState(false)
  const [issuingId, setIssuingId] = useState<string | null>(null)
  const [issueResult, setIssueResult] = useState<any>(null)
  const [autoCreating, setAutoCreating] = useState(false)
  const [verifyingId, setVerifyingId] = useState<string | null>(null)
  const [verifyResult, setVerifyResult] = useState<any>(null)
  const [verifyModalOpen, setVerifyModalOpen] = useState(false)
  const [autoIssuing, setAutoIssuing] = useState(false)
  const [selected, setSelected] = useState<any>(null)
  const [form] = Form.useForm()

  // 风险评估
  const [riskResult, setRiskResult] = useState<any>(null)
  const [riskChecking, setRiskChecking] = useState(false)
  const [riskOpen, setRiskOpen] = useState(false)

  const { currentClientId } = useClient()
  const { isClient } = useRole()
  const { message } = App.useApp()

  const fetchInvoices = async () => {
    setLoading(true)
    try {
      const res: any = await invoiceApi.list({ page_size: 50, client_id: currentClientId })
      setInvoices(res.items || [])
    } catch { message.error('加载开票列表失败') }
    setLoading(false)
  }

  useEffect(() => { fetchInvoices() }, [currentClientId])

  const handleCreate = async () => {
    const values = await form.validateFields()
    const idempotencyKey = crypto.randomUUID()

    // 计算价税合计
    const items = values.items || []
    let grandTotal = 0
    for (const it of items) {
      const amount = parseFloat(it.amount || '0') || 0
      const taxAmount = parseFloat(it.tax_amount || '0') || 0
      grandTotal += amount + taxAmount
    }

    // 创建前风险评估
    const riskData = { ...values, client_id: currentClientId, grand_total: grandTotal, items }
    try {
      const risk: any = await invoiceApi.riskCheck(riskData)
      if (risk.require_review) {
        setRiskResult(risk)
        setRiskOpen(true)
        // 用户确认后继续
        Modal.confirm({
          title: '风险评估警告',
          icon: <WarningOutlined style={{ color: '#dc2626' }} />,
          content: `该发票风险等级为「${RISK_LABELS[risk.risk_level] || risk.risk_level}」（${risk.score}分）。${risk.recommendations?.join('；')}`,
          okText: '仍然创建',
          cancelText: '取消',
          okButtonProps: { danger: true },
          onOk: async () => {
            try {
              await invoiceApi.create({ ...values, client_id: currentClientId, idempotency_key: idempotencyKey, grand_total: grandTotal })
              message.success('开票申请已创建')
              setCreateOpen(false); form.resetFields(); fetchInvoices()
            } catch (e: any) { message.error(e?.response?.data?.detail || '创建失败') }
          },
        })
        return
      }
    } catch { /* risk check failed, proceed anyway */ }

    try {
      await invoiceApi.create({ ...values, client_id: currentClientId, idempotency_key: idempotencyKey, grand_total: grandTotal })
      message.success('开票申请已创建')
      setCreateOpen(false); form.resetFields(); fetchInvoices()
    } catch (e: any) { message.error(e?.response?.data?.detail || '创建失败') }
  }

  const handleIssue = async (record: any) => {
    setIssuingId(record.id)
    setIssueResult(null)
    try {
      const res: any = await invoiceApi.issue(record.id)
      setIssueResult(res)
      if (res.success) {
        message.success('发票开具成功！')
      } else {
        message.warning(res.message)
      }
      fetchInvoices()
    } catch (e: any) {
      const detail = e?.response?.data?.detail
      if (detail?.code === 'RISK_BLOCKED') {
        setRiskResult(detail.risk)
        setRiskOpen(true)
        message.error(detail.message)
      } else {
        message.error(typeof detail === 'string' ? detail : '开票失败，请检查电子税务局凭据配置')
      }
    }
    setIssuingId(null)
  }

  const handleAutoCreate = async () => {
    if (!currentClientId) { message.warning('请先选择客户'); return }
    setAutoCreating(true)
    try {
      const res: any = await rpaApi.autoCreateInvoices(currentClientId)
      if (res.invoices_created > 0) {
        message.success(`已从凭证自动生成 ${res.invoices_created} 张开票草稿`)
      } else {
        message.info(res.details?.[0] || '未发现需要开票的销项凭证')
      }
      fetchInvoices()
    } catch (e: any) { message.error(e?.detail || '自动创建发票失败') }
    setAutoCreating(false)
  }

  const handlePrecheckRisk = async (record: any) => {
    setRiskChecking(true)
    setRiskResult(null)
    try {
      const res: any = await invoiceApi.riskCheck({
        buyer_tax_no: record.buyer_tax_no,
        buyer_name: record.buyer_name,
        grand_total: parseFloat(record.grand_total || '0'),
        items: record.items || [],
        client_id: currentClientId,
      })
      setRiskResult(res)
      setRiskOpen(true)
    } catch (e: any) { message.error('风险评估失败') }
    setRiskChecking(false)
  }

  const handleAutoIssueAll = async () => {
    if (!currentClientId) { message.warning('请先选择客户'); return }
    const draftCount = invoices.filter(i => i.status === 'draft').length
    if (draftCount === 0) { message.info('没有待开具的发票草稿'); return }
    Modal.confirm({
      title: '一键批量开票',
      content: `将自动提交 ${draftCount} 张发票至电子税务局，预计需要 ${draftCount * 15} 秒。系统将自动进行风险评估。`,
      onOk: async () => {
        setAutoIssuing(true)
        try {
          const res: any = await rpaApi.autoIssueAllInvoices(currentClientId)
          if (res.failed_count > 0) {
            message.warning(res.message)
          } else {
            message.success(res.message)
          }
          fetchInvoices()
        } catch (e: any) { message.error(e?.detail || '批量开票失败') }
        setAutoIssuing(false)
      },
    })
  }

  const handleVerify = async (record: any) => {
    setVerifyingId(record.id)
    setVerifyResult(null)
    setVerifyModalOpen(true)
    try {
      const res: any = await verifyApi.verifySystemInvoice(record.id)
      setVerifyResult(res)
      if (res.is_valid) { message.success('发票查验通过') }
      else { message.warning(res.message || '查验结果异常') }
    } catch (e: any) { setVerifyResult({ success: false, message: e?.detail || '查验请求失败' }); message.error('查验失败') }
    setVerifyingId(null)
  }

  const columns: ColumnsType<any> = [
    { title: '购方名称', dataIndex: 'buyer_name', width: 180, ellipsis: true },
    { title: '纳税人识别号', dataIndex: 'buyer_tax_no', width: 170 },
    {
      title: '发票类型', dataIndex: 'invoice_type', width: 110,
      render: (t: string) => <Tag>{t === 'electronic_normal' ? '电子普通发票' : '电子专用发票'}</Tag>,
    },
    {
      title: '价税合计', dataIndex: 'grand_total', width: 120, align: 'right' as const,
      render: (v: string) => v ? `¥${parseFloat(v).toLocaleString()}` : '-',
    },
    {
      title: '状态', dataIndex: 'status', width: 90,
      render: (s: string) => {
        const map: Record<string, { color: string; text: string }> = {
          draft: { color: 'default', text: '草稿' }, issuing: { color: 'processing', text: '开票中' },
          issued: { color: 'green', text: '已开具' }, failed: { color: 'red', text: '失败' },
        }
        const m = map[s] || { color: 'default', text: s }
        return <Tag color={m.color}>{m.text}</Tag>
      },
    },
    { title: '开票时间', dataIndex: 'issued_at', width: 150, render: (v: string) => v ? v.slice(0, 19) : '-' },
    {
      title: '操作', key: 'actions', width: 260,
      render: (_: any, record: any) => (
        <Space size={0}>
          <Button type="link" size="small" icon={<EyeOutlined />} onClick={() => { setSelected(record); setDetailOpen(true) }}>详情</Button>
          {!isClient && record.status === 'draft' && (
            <>
              <Button type="link" size="small" icon={<SafetyCertificateOutlined />} loading={riskChecking}
                onClick={() => handlePrecheckRisk(record)} style={{ color: '#d97706' }}>风控</Button>
              <Button type="link" size="small" icon={<RocketOutlined />} style={{ color: '#2563eb' }}
                loading={issuingId === record.id} onClick={() => handleIssue(record)}>开票</Button>
            </>
          )}
          {!isClient && record.status === 'failed' && (
            <Button type="link" size="small" icon={<SendOutlined />} onClick={() => handleIssue(record)}>重试</Button>
          )}
          {record.status === 'issued' && record.invoice_code && (
            <Button type="link" size="small" icon={<SafetyCertificateOutlined />} loading={verifyingId === record.id}
              onClick={() => handleVerify(record)} style={{ color: '#16a34a' }}>查验</Button>
          )}
          {!isClient && record.status !== 'issued' && (
            <Popconfirm title="确认删除?" onConfirm={async () => {
              try { await invoiceApi.delete(record.id); message.success('已删除'); fetchInvoices() } catch { message.error('删除失败') }
            }}>
              <Button type="link" size="small" danger icon={<DeleteOutlined />} />
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ]

  const draftCount = invoices.filter(i => i.status === 'draft').length
  const issuedCount = invoices.filter(i => i.status === 'issued').length
  const failedCount = invoices.filter(i => i.status === 'failed').length

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <div>
          <h2 style={{ margin: 0 }}>开票中心</h2>
          <Text type="secondary" style={{ fontSize: 12 }}>
            数电票（全电发票）· 智能风控 · Playwright 自动开票 · 发票真伪查验
          </Text>
        </div>
        {!isClient && (
          <Space>
            <Button icon={<RobotOutlined />} loading={autoCreating} onClick={handleAutoCreate}
              style={{ color: '#7c3aed', borderColor: '#7c3aed' }}>自动识别开票</Button>
            <Button icon={<ThunderboltOutlined />} loading={autoIssuing} onClick={handleAutoIssueAll}
              style={{ color: '#dc2626', borderColor: '#dc2626' }}
              disabled={draftCount === 0}>一键全部开具 ({draftCount})</Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => { form.resetFields(); setCreateOpen(true) }}>
              新增开票
            </Button>
          </Space>
        )}
      </div>

      {/* 统计卡片 */}
      <Row gutter={12} style={{ marginBottom: 16 }}>
        <Col span={6}><Card size="small"><div style={{ textAlign: 'center', fontSize: 24, fontWeight: 700, color: '#2563eb' }}>{invoices.length}</div><div style={{ textAlign: 'center', fontSize: 12, color: '#64748b' }}>总发票</div></Card></Col>
        <Col span={6}><Card size="small"><div style={{ textAlign: 'center', fontSize: 24, fontWeight: 700, color: '#d97706' }}>{draftCount}</div><div style={{ textAlign: 'center', fontSize: 12, color: '#64748b' }}>待开票</div></Card></Col>
        <Col span={6}><Card size="small"><div style={{ textAlign: 'center', fontSize: 24, fontWeight: 700, color: '#16a34a' }}>{issuedCount}</div><div style={{ textAlign: 'center', fontSize: 12, color: '#64748b' }}>已开票</div></Card></Col>
        <Col span={6}><Card size="small"><div style={{ textAlign: 'center', fontSize: 24, fontWeight: 700, color: '#dc2626' }}>{failedCount}</div><div style={{ textAlign: 'center', fontSize: 12, color: '#64748b' }}>失败</div></Card></Col>
      </Row>

      {issueResult?.success && (
        <Card style={{ marginBottom: 16, borderColor: '#52c41a' }}>
          <Result status="success" title="发票开具成功" subTitle={issueResult.message} />
        </Card>
      )}

      {loading ? (
        <SkeletonTable rows={5} columns={6} />
      ) : invoices.length === 0 ? (
        <Card>
          <EmptyState title="暂无开票记录" description={isClient ? '请联系您的专属服务人员' : '点击「新增开票」创建第一张发票'}
            icon={<InboxOutlined style={{ fontSize: 64, color: '#d9d9d9' }} />}
            {...(!isClient && { actionLabel: '新增开票', onAction: () => setCreateOpen(true) })} />
        </Card>
      ) : (
        <Card style={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
          <Table dataSource={invoices} columns={columns} rowKey="id" scroll={{ x: 1100 }} />
        </Card>
      )}

      {/* ===== 新增开票弹窗 ===== */}
      <Modal title="新增开票申请" open={createOpen} onOk={handleCreate} onCancel={() => setCreateOpen(false)} width={800} okText="保存草稿（含风险评估）">
        <Form form={form} layout="vertical" initialValues={{ invoice_type: 'electronic_normal' }}>
          <Alert message="系统将在保存前自动进行多维度风险评估：购方税号校验、重复检测、金额合理性、税率检查" type="info" showIcon style={{ marginBottom: 12 }} />
          <Title level={5} style={{ fontSize: 14, marginBottom: 8 }}>购方信息</Title>
          <Row gutter={16}>
            <Col span={12}><Form.Item label="购方名称" name="buyer_name" rules={[{ required: true }]}><Input /></Form.Item></Col>
            <Col span={12}><Form.Item label="纳税人识别号" name="buyer_tax_no" rules={[{ required: true, pattern: /^[0-9A-HJ-NPQRTUWXY]{18}$/, message: '18位统一社会信用代码' }]}><Input maxLength={18} /></Form.Item></Col>
          </Row>
          <Row gutter={16}>
            <Col span={8}><Form.Item label="购方地址" name="buyer_address"><Input /></Form.Item></Col>
            <Col span={8}><Form.Item label="电话" name="buyer_phone"><Input /></Form.Item></Col>
            <Col span={8}><Form.Item label="开户银行" name="buyer_bank"><Input /></Form.Item></Col>
          </Row>
          <Divider style={{ margin: '8px 0' }} />
          <Title level={5} style={{ fontSize: 14, marginBottom: 8 }}>开票信息</Title>
          <Row gutter={16}>
            <Col span={8}><Form.Item label="发票类型" name="invoice_type"><Select options={[{ label: '电子普通发票', value: 'electronic_normal' }, { label: '电子专用发票', value: 'electronic_special' }]} /></Form.Item></Col>
          </Row>
          <Form.List name="items" initialValue={[{ name: '', spec: '', unit: '', quantity: 1, price: 0, tax_rate: 0.13, amount: 0, tax_amount: 0 }]}>
            {(fields, { add, remove }) => (
              <>
                {fields.map(({ key, name, ...rest }) => (
                  <Row key={key} gutter={8} style={{ marginBottom: 6 }} align="middle">
                    <Col span={4}><Form.Item {...rest} name={[name, 'name']} label="货物名称" style={{ marginBottom: 0 }}><Input size="small" /></Form.Item></Col>
                    <Col span={2}><Form.Item {...rest} name={[name, 'spec']} label="规格" style={{ marginBottom: 0 }}><Input size="small" /></Form.Item></Col>
                    <Col span={2}><Form.Item {...rest} name={[name, 'unit']} label="单位" style={{ marginBottom: 0 }}><Input size="small" /></Form.Item></Col>
                    <Col span={2}><Form.Item {...rest} name={[name, 'quantity']} label="数量" style={{ marginBottom: 0 }}><InputNumber size="small" min={1} style={{ width: '100%' }} /></Form.Item></Col>
                    <Col span={3}><Form.Item {...rest} name={[name, 'price']} label="单价" style={{ marginBottom: 0 }}><InputNumber size="small" min={0} precision={2} style={{ width: '100%' }} /></Form.Item></Col>
                    <Col span={3}><Form.Item {...rest} name={[name, 'amount']} label="金额" style={{ marginBottom: 0 }}><InputNumber size="small" min={0} precision={2} style={{ width: '100%' }} /></Form.Item></Col>
                    <Col span={3}><Form.Item {...rest} name={[name, 'tax_rate']} label="税率" style={{ marginBottom: 0 }}><Select size="small" options={[{ label: '13%', value: 0.13 }, { label: '9%', value: 0.09 }, { label: '6%', value: 0.06 }, { label: '3%', value: 0.03 }, { label: '0%', value: 0 }]} /></Form.Item></Col>
                    <Col span={3}><Form.Item {...rest} name={[name, 'tax_amount']} label="税额" style={{ marginBottom: 0 }}><InputNumber size="small" min={0} precision={2} style={{ width: '100%' }} /></Form.Item></Col>
                    <Col span={1}><Button size="small" danger onClick={() => remove(name)} style={{ marginTop: 24 }}>x</Button></Col>
                  </Row>
                ))}
                <Button type="dashed" onClick={() => add({ name: '', spec: '', unit: '', quantity: 1, price: 0, tax_rate: 0.13 })} block size="small">+ 添加商品</Button>
              </>
            )}
          </Form.List>
          <Divider style={{ margin: '8px 0' }} />
          <Form.Item label="备注" name="remark"><TextArea rows={2} /></Form.Item>
        </Form>
      </Modal>

      {/* ===== 详情弹窗 ===== */}
      <Modal title="开票详情" open={detailOpen} onCancel={() => setDetailOpen(false)} footer={null} width={800}>
        {selected && (<>
          <div style={{ marginBottom: 16 }}><Tag color={selected.status === 'issued' ? 'green' : 'default'}>{selected.status}</Tag><Text type="secondary" style={{ marginLeft: 8 }}>创建时间：{selected.created_at?.slice(0, 19)}</Text></div>
          <Row gutter={16}>
            <Col span={12}><Text strong>购方名称：</Text>{selected.buyer_name}</Col>
            <Col span={12}><Text strong>税号：</Text>{selected.buyer_tax_no}</Col>
            <Col span={12}><Text strong>发票类型：</Text>{selected.invoice_type === 'electronic_normal' ? '电子普通发票' : '电子专用发票'}</Col>
            <Col span={12}><Text strong>价税合计：</Text>¥{parseFloat(selected.grand_total || '0').toLocaleString()}</Col>
          </Row>
          <Divider />
          <Table dataSource={(selected.items || []).map((it: any, i: number) => ({ ...it, key: i }))} size="small" pagination={false}
            columns={[
              { title: '名称', dataIndex: 'name' }, { title: '规格', dataIndex: 'spec' }, { title: '数量', dataIndex: 'quantity' },
              { title: '单价', dataIndex: 'price', render: (v: number) => `¥${v}` },
              { title: '金额', dataIndex: 'amount', render: (v: number) => v ? `¥${v}` : '-' },
              { title: '税率', dataIndex: 'tax_rate', render: (v: number) => v ? `${(v * 100).toFixed(0)}%` : '-' },
              { title: '税额', dataIndex: 'tax_amount', render: (v: number) => v ? `¥${v}` : '-' },
            ]} />
        </>)}
      </Modal>

      {/* ===== 风险评估弹窗 ===== */}
      <Modal title={<Space><SafetyCertificateOutlined />开票风险评估报告</Space>} open={riskOpen}
        onCancel={() => setRiskOpen(false)} footer={<Button onClick={() => setRiskOpen(false)}>关闭</Button>} width={640}>
        {riskResult && (
          <div>
            <div style={{ textAlign: 'center', marginBottom: 20 }}>
              <Progress type="dashboard" percent={riskResult.score} format={() => `${riskResult.score}分`}
                strokeColor={riskResult.score >= 60 ? '#dc2626' : riskResult.score >= 35 ? '#d97706' : riskResult.score >= 15 ? '#f59e0b' : '#16a34a'}
                status={riskResult.score >= 60 ? 'exception' : riskResult.score >= 35 ? 'active' : 'normal'} />
              <div style={{ marginTop: 8 }}>
                <Tag color={RISK_COLORS[riskResult.risk_level]} style={{ fontSize: 14, padding: '4px 16px' }}>
                  {RISK_LABELS[riskResult.risk_level] || riskResult.risk_level}
                </Tag>
              </div>
            </div>
            <Table dataSource={riskResult.checks || []} rowKey="name" size="small" pagination={false}
              columns={[
                { title: '检查项', dataIndex: 'name', width: 120 },
                { title: '结果', dataIndex: 'passed', width: 70, render: (v: boolean) => v ? <Tag color="green">通过</Tag> : <Tag color="red">异常</Tag> },
                { title: '详情', dataIndex: 'detail' },
                { title: '权重', dataIndex: 'weight', width: 60, render: (v: number) => `${v}%` },
              ]} />
            {riskResult.recommendations?.length > 0 && (
              <Alert type="warning" showIcon message="优化建议" description={riskResult.recommendations.map((r: string, i: number) => <div key={i}>• {r}</div>)} style={{ marginTop: 12 }} />
            )}
          </div>
        )}
      </Modal>

      {/* ===== 发票查验弹窗 ===== */}
      <Modal title="发票真伪查验" open={verifyModalOpen} onCancel={() => setVerifyModalOpen(false)}
        footer={<Button onClick={() => setVerifyModalOpen(false)}>关闭</Button>} width={600}>
        {verifyingId ? (
          <div style={{ textAlign: 'center', padding: 40 }}><Spin size="large" /><div style={{ marginTop: 16 }}>正在连接国家税务总局发票查验平台…</div></div>
        ) : verifyResult ? (
          verifyResult.success ? (
            <div>
              <Result status={verifyResult.is_valid ? 'success' : 'warning'}
                title={verifyResult.is_valid ? '发票查验通过' : (verifyResult.message || '查验结果异常')}
                subTitle={`发票代码: ${verifyResult.invoice_code} / 发票号码: ${verifyResult.invoice_no}`} />
              {verifyResult.details && (
                <Descriptions bordered size="small" column={2} style={{ marginTop: 16 }}>
                  <Descriptions.Item label="发票类型">{verifyResult.details.invoice_type || '-'}</Descriptions.Item>
                  <Descriptions.Item label="开票日期">{verifyResult.details.invoice_date || '-'}</Descriptions.Item>
                  <Descriptions.Item label="销售方">{verifyResult.details.seller_name || '-'}</Descriptions.Item>
                  <Descriptions.Item label="购买方">{verifyResult.details.buyer_name || '-'}</Descriptions.Item>
                  <Descriptions.Item label="金额(不含税)">{verifyResult.details.total_amount || '-'}</Descriptions.Item>
                  <Descriptions.Item label="税额">{verifyResult.details.tax_amount || '-'}</Descriptions.Item>
                  <Descriptions.Item label="价税合计" span={2}>{verifyResult.details.grand_total || '-'}</Descriptions.Item>
                </Descriptions>
              )}
            </div>
          ) : <Result status="error" title="查验失败" subTitle={verifyResult.message} />
        ) : null}
      </Modal>
    </div>
  )
}
