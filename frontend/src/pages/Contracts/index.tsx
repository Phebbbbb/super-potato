import { useState, useEffect } from 'react'
import { Card, Table, Button, Space, Tag, Modal, Form, Input, Select, InputNumber, DatePicker, App, Row, Col, Statistic, Typography, Badge, Tooltip, Descriptions, Tabs } from 'antd'
import { PlusOutlined, EditOutlined, DeleteOutlined, FileTextOutlined, WarningOutlined, CopyOutlined, FileAddOutlined, DownloadOutlined, PrinterOutlined, SafetyCertificateOutlined, HistoryOutlined } from '@ant-design/icons'
import { contractApi } from '@/services/api'
import { useClient } from '@/contexts/ClientContext'
import { useRole } from '@/hooks/useRole'
import SkeletonTable from '@/components/SkeletonTable'
import EmptyState from '@/components/EmptyState'
import dayjs from 'dayjs'

const { Text } = Typography

const TYPE_OPTIONS = [
  { label: '服务合同', value: 'service' },
  { label: '销售合同', value: 'sales' },
  { label: '采购合同', value: 'purchase' },
  { label: '租赁合同', value: 'lease' },
  { label: '其他', value: 'other' },
]

const STATUS_OPTIONS = [
  { label: '生效中', value: 'active' },
  { label: '已到期', value: 'expired' },
  { label: '已终止', value: 'terminated' },
  { label: '已完成', value: 'completed' },
]

export default function Contracts() {
  const [contracts, setContracts] = useState<any[]>([])
  const [templates, setTemplates] = useState<any[]>([])
  const [loading, setLoading] = useState(false)

  const [createOpen, setCreateOpen] = useState(false)
  const [editOpen, setEditOpen] = useState(false)
  const [tplEditOpen, setTplEditOpen] = useState(false)
  const [selected, setSelected] = useState<any>(null)
  const [expiringCount, setExpiringCount] = useState(0)
  const [form] = Form.useForm()
  const [editForm] = Form.useForm()
  const [tplForm] = Form.useForm()

  // ===== 电子签 state =====
  const [esignOpen, setEsignOpen] = useState(false)
  const [esignSending, setEsignSending] = useState(false)
  const [esignLogOpen, setEsignLogOpen] = useState(false)
  const [esignLogs, setEsignLogs] = useState<any[]>([])
  const [esignForm] = Form.useForm()
  const [activeTab, setActiveTab] = useState('contracts')
  const { currentClientId } = useClient()
  const { isClient } = useRole()
  const { message } = App.useApp()

  const fetchContracts = async () => {
    if (!currentClientId) return
    setLoading(true)
    try {
      const res: any = await contractApi.list({ client_id: currentClientId })
      setContracts(res.items || [])
      setExpiringCount(res.expiring_count || 0)
    } catch { message.error('加载合同列表失败') }
    setLoading(false)
  }

  const fetchTemplates = async () => {
    try {
      const res: any = await contractApi.templates()
      setTemplates(res.items || [])
    } catch { /* ignore */ }
  }

  useEffect(() => { fetchContracts(); fetchTemplates() }, [currentClientId])

  // ===== 已签合同操作 =====
  const handleCreate = async () => {
    const values = await form.validateFields()
    try {
      const res: any = await contractApi.create({
        ...values,
        client_id: currentClientId,
        start_date: values.date_range?.[0]?.format('YYYY-MM-DD'),
        end_date: values.date_range?.[1]?.format('YYYY-MM-DD'),
      })
      message.success(res.message || '合同已创建')
      setCreateOpen(false); form.resetFields(); fetchContracts()
    } catch (e: any) { message.error(e?.response?.data?.detail || '创建失败') }
  }

  const handleEdit = (record: any) => {
    setSelected(record)
    editForm.setFieldsValue({
      contract_name: record.contract_name, contract_type: record.contract_type,
      counterparty: record.counterparty, amount: record.amount,
      contract_no: record.contract_no, payment_terms: record.payment_terms,
      revenue_period: record.revenue_period, monthly_revenue: record.monthly_revenue,
      remark: record.remark, status: record.status,
      date_range: [record.start_date ? dayjs(record.start_date) : null, record.end_date ? dayjs(record.end_date) : null],
    })
    setEditOpen(true)
  }

  const handleEditSave = async () => {
    const values = await editForm.validateFields()
    try {
      await contractApi.update(selected.id, {
        ...values,
        start_date: values.date_range?.[0]?.format('YYYY-MM-DD'),
        end_date: values.date_range?.[1]?.format('YYYY-MM-DD'),
      })
      message.success('合同已更新')
      setEditOpen(false); fetchContracts()
    } catch (e: any) { message.error(e?.response?.data?.detail || '更新失败') }
  }

  const handleDelete = async (record: any) => {
    Modal.confirm({
      title: '确认删除', content: `删除合同: ${record.contract_name}?`,
      onOk: async () => {
        try { await contractApi.delete(record.id); message.success('已删除'); fetchContracts(); fetchTemplates() }
        catch { message.error('删除失败') }
      },
    })
  }

  // ===== 下载合同 =====
  const buildContractHTML = (c: any) => {
    const typeLabel = TYPE_OPTIONS.find(o => o.value === c.contract_type)?.label || c.contract_type
    const statusLabel = STATUS_OPTIONS.find(o => o.value === c.status)?.label || c.status
    const revLabel: Record<string, string> = { monthly: '按月确认', quarterly: '按季确认', once: '一次性确认' }
    return `<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><title>${c.contract_name}</title>
<style>
  body { font-family: "SimSun", serif; max-width: 720px; margin: 40px auto; padding: 0 20px; color: #1e293b; line-height: 1.8; }
  h1 { text-align: center; font-size: 22px; letter-spacing: 2px; margin-bottom: 8px; }
  .no { text-align: center; font-size: 13px; color: #64748b; margin-bottom: 20px; }
  table { width: 100%; border-collapse: collapse; margin: 16px 0; }
  table td { padding: 8px 12px; border: 1px solid #cbd5e1; font-size: 14px; }
  table td:first-child { width: 120px; background: #f1f5f9; font-weight: bold; }
  .footer { margin-top: 30px; font-size: 13px; display: flex; justify-content: space-between; }
  .stamp { margin-top: 40px; text-align: right; }
  @media print { body { margin: 0; padding: 20px; } }
</style></head>
<body>
  <h1>${c.contract_name}</h1>
  <div class="no">合同编号：${c.contract_no || '-'}</div>
  <table>
    <tr><td>合同类型</td><td>${typeLabel}</td></tr>
    <tr><td>对方单位</td><td>${c.counterparty || '-'}</td></tr>
    <tr><td>合同金额</td><td>¥${(c.amount || 0).toLocaleString()}</td></tr>
    <tr><td>合同期间</td><td>${c.start_date || '-'} 至 ${c.end_date || '-'}</td></tr>
    <tr><td>当前状态</td><td>${statusLabel}</td></tr>
    <tr><td>付款条款</td><td>${c.payment_terms || '-'}</td></tr>
    <tr><td>收入确认周期</td><td>${revLabel[c.revenue_period] || c.revenue_period || '-'}</td></tr>
    <tr><td>月均确认收入</td><td>¥${(c.monthly_revenue || 0).toLocaleString()}</td></tr>
    <tr><td>备注</td><td>${c.remark || '-'}</td></tr>
  </table>
  <div class="footer">
    <span>签约日期：${c.start_date || '-'}</span>
    <span>打印时间：${new Date().toLocaleDateString('zh-CN')}</span>
  </div>
  <div class="stamp">（盖章处）</div>
</body></html>`
  }

  const handleDownload = (record: any) => {
    const html = buildContractHTML(record)
    const blob = new Blob([html], { type: 'text/html;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${record.contract_name}_${record.contract_no || ''}.html`
    a.click()
    URL.revokeObjectURL(url)
    message.success('合同已下载')
  }

  const handlePrint = (record: any) => {
    const html = buildContractHTML(record)
    const w = window.open('', '_blank', 'width=800,height=600')
    if (!w) { message.error('请允许弹出窗口以打印合同'); return }
    w.document.write(html)
    w.document.close()
    w.focus()
    w.onload = () => { w.print(); w.close() }
    // fallback if onload doesn't fire
    setTimeout(() => { try { w.print(); w.close() } catch { /* ignore */ } }, 800)
  }

  // ===== 电子签 =====
  const ESIGN_PLATFORMS = [
    { label: '法大大', value: 'fadada', desc: '国内领先的电子签章平台' },
    { label: '上上签', value: 'bestsign', desc: '企业级电子签约云平台' },
    { label: '契约锁', value: 'qiyuesuo', desc: '电子合同与实体印章统一管理' },
    { label: 'e签宝', value: 'esign', desc: '中国最大的电子签名平台之一' },
  ]

  const handleOpenEsign = (record: any) => {
    setSelected(record)
    esignForm.resetFields()
    esignForm.setFieldsValue({
      platform: '',
      signer_name: record.counterparty || '',
      signer_phone: '',
    })
    setEsignOpen(true)
  }

  const [esignResult, setEsignResult] = useState<any>(null)
  const [esignResultOpen, setEsignResultOpen] = useState(false)

  const handleSendEsign = async () => {
    const values = await esignForm.validateFields()
    setEsignSending(true)
    try {
      const res: any = await contractApi.sendEsign(selected.id, values)
      setEsignResult(res)
      setEsignOpen(false)
      setEsignResultOpen(true)
      fetchContracts()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '发送电子签失败')
    }
    setEsignSending(false)
  }

  const copySignLink = () => {
    if (!esignResult?.sign_link) return
    const fullLink = `${window.location.origin}${esignResult.sign_link}`
    navigator.clipboard.writeText(fullLink).then(() => {
      message.success('签署链接已复制到剪贴板')
    }).catch(() => {
      // fallback
      const ta = document.createElement('textarea')
      ta.value = fullLink
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
      message.success('签署链接已复制')
    })
  }

  const handleUpdateEsignStatus = async (record: any, newStatus: string) => {
    try {
      await contractApi.updateEsignStatus(record.id, { e_sign_status: newStatus })
      const labels: Record<string, string> = { signed: '已签署', expired: '已过期', rejected: '已拒签' }
      message.success(`电子签状态已更新：${labels[newStatus] || newStatus}`)
      fetchContracts()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '更新失败')
    }
  }

  const handleEsignLog = async (record: any) => {
    setSelected(record)
    try {
      const res: any = await contractApi.esignLog(record.id)
      setEsignLogs(res.items || [])
    } catch { setEsignLogs([]) }
    setEsignLogOpen(true)
  }

  // ===== 从模板创建合同 =====
  const handleCreateFromTemplate = (tpl: any) => {
    form.setFieldsValue({
      contract_name: tpl.contract_name,
      contract_type: tpl.contract_type,
      counterparty: '',
      amount: tpl.amount,
      payment_terms: tpl.payment_terms,
      revenue_period: tpl.revenue_period,
      monthly_revenue: tpl.monthly_revenue,
      remark: tpl.remark,
    })
    setSelected(tpl)
    setCreateOpen(true)
  }

  // ===== 模板管理 =====
  const handleAddTemplate = () => {
    tplForm.resetFields()
    tplForm.setFieldsValue({ contract_type: 'service', amount: 0, revenue_period: 'monthly' })
    setTplEditOpen(true)
  }

  const handleEditTemplate = (tpl: any) => {
    setSelected(tpl)
    tplForm.setFieldsValue({
      contract_name: tpl.contract_name, contract_type: tpl.contract_type,
      counterparty: tpl.counterparty, amount: tpl.amount,
      payment_terms: tpl.payment_terms, revenue_period: tpl.revenue_period,
      monthly_revenue: tpl.monthly_revenue, remark: tpl.remark,
    })
    setTplEditOpen(true)
  }

  const handleSaveTemplate = async () => {
    const values = await tplForm.validateFields()
    try {
      if (selected?.id && selected?.is_template) {
        await contractApi.update(selected.id, values)
        message.success('模板已更新')
      } else {
        await contractApi.create({
          ...values,
          is_template: true,
          start_date: dayjs().format('YYYY-MM-DD'),
          end_date: dayjs().add(1, 'year').format('YYYY-MM-DD'),
        })
        message.success('合同模板已创建')
      }
      setTplEditOpen(false); setSelected(null); fetchTemplates()
    } catch (e: any) { message.error(e?.response?.data?.detail || '保存失败') }
  }

  // ===== 已签合同列 =====
  const signedColumns = [
    { title: '合同编号', dataIndex: 'contract_no', width: 130 },
    { title: '合同名称', dataIndex: 'contract_name', width: 180, ellipsis: true },
    { title: '类型', dataIndex: 'contract_type', width: 90, render: (t: string) => <Tag>{TYPE_OPTIONS.find(o => o.value === t)?.label || t}</Tag> },
    { title: '对方单位', dataIndex: 'counterparty', width: 150, ellipsis: true },
    { title: '金额', dataIndex: 'amount', width: 120, align: 'right' as const, render: (v: number) => `¥${v.toLocaleString()}` },
    { title: '起始日', dataIndex: 'start_date', width: 100 },
    {
      title: '到期日', dataIndex: 'end_date', width: 100,
      render: (v: string, r: any) => (
        <Space size={4}>
          <Text style={{ color: r.expiring_soon ? '#dc2626' : undefined }}>{v}</Text>
          {r.expiring_soon && <Badge status="error" />}
        </Space>
      ),
    },
    {
      title: '状态', dataIndex: 'status', width: 90,
      render: (s: string) => {
        const m: Record<string, { color: string; text: string }> = {
          active: { color: 'green', text: '生效中' }, expired: { color: 'red', text: '已到期' },
          terminated: { color: 'default', text: '已终止' }, completed: { color: 'blue', text: '已完成' },
        }
        return <Tag color={(m[s] || {}).color}>{(m[s] || {}).text || s}</Tag>
      },
    },
    { title: '月均收入', dataIndex: 'monthly_revenue', width: 100, align: 'right' as const, render: (v: number) => v ? `¥${v.toLocaleString()}` : '-' },
    {
      title: '电子签', dataIndex: 'e_sign_status', width: 100,
      render: (s: string, r: any) => {
        if (!s) return <Tag color="default">未发起</Tag>
        const m: Record<string, { color: string; text: string }> = {
          sent: { color: 'processing', text: '待签署' },
          signed: { color: 'green', text: '已签署' },
          expired: { color: 'red', text: '已过期' },
          rejected: { color: 'orange', text: '已拒签' },
        }
        const info = m[s] || { color: 'default', text: s }
        const platform = r.e_sign_platform ? ` · ${ESIGN_PLATFORMS.find(p => p.value === r.e_sign_platform)?.label || r.e_sign_platform}` : ''
        return (
          <Tooltip title={r.e_sign_signer_name ? `签署人: ${r.e_sign_signer_name} (${r.e_sign_signer_phone})${platform}` : ''}>
            <Tag color={info.color}>{info.text}</Tag>
          </Tooltip>
        )
      },
    },
    {
      title: '操作', width: 360,
      render: (_: any, r: any) => (
        <Space size={4} wrap>
          <Button size="small" icon={<DownloadOutlined />} onClick={() => handleDownload(r)}>下载</Button>
          <Button size="small" icon={<PrinterOutlined />} onClick={() => handlePrint(r)}>打印</Button>
          {!isClient && !r.e_sign_status && (
            <Button size="small" icon={<SafetyCertificateOutlined />} onClick={() => handleOpenEsign(r)} style={{ color: '#2563eb', borderColor: '#2563eb' }}>电子签</Button>
          )}
          {!isClient && r.e_sign_status === 'sent' && (
            <>
              <Button size="small" onClick={() => handleUpdateEsignStatus(r, 'signed')} style={{ color: '#16a34a', borderColor: '#16a34a' }}>标记已签</Button>
              <Button size="small" onClick={() => handleUpdateEsignStatus(r, 'expired')} style={{ color: '#d97706', borderColor: '#d97706' }}>过期</Button>
            </>
          )}
          {!isClient && r.e_sign_status && (
            <Button size="small" icon={<HistoryOutlined />} onClick={() => handleEsignLog(r)}>记录</Button>
          )}
          {!isClient && (
            <>
              <Button size="small" icon={<EditOutlined />} onClick={() => handleEdit(r)}>编辑</Button>
              <Button size="small" danger icon={<DeleteOutlined />} onClick={() => handleDelete(r)}>删除</Button>
            </>
          )}
        </Space>
      ),
    },
  ]

  // ===== 模板列 =====
  const templateColumns = [
    { title: '模板名称', dataIndex: 'contract_name', width: 220, ellipsis: true,
      render: (v: string) => <Text strong>{v}</Text> },
    { title: '类型', dataIndex: 'contract_type', width: 90, render: (t: string) => <Tag color="purple">{TYPE_OPTIONS.find(o => o.value === t)?.label || t}</Tag> },
    { title: '对方称呼', dataIndex: 'counterparty', width: 140 },
    { title: '默认金额', dataIndex: 'amount', width: 120, align: 'right' as const, render: (v: number) => `¥${v.toLocaleString()}` },
    { title: '收入确认', dataIndex: 'revenue_period', width: 90,
      render: (v: string) => {
        const m: Record<string, string> = { monthly: '按月', quarterly: '按季', once: '一次性' }
        return m[v] || v
      } },
    { title: '付款条款', dataIndex: 'payment_terms', width: 180, ellipsis: true },
    {
      title: '操作', width: 260,
      render: (_: any, r: any) => (
        <Space size={4} wrap>
          <Button size="small" icon={<FileAddOutlined />} onClick={() => handleCreateFromTemplate(r)}>创建合同</Button>
          <Button size="small" icon={<EditOutlined />} onClick={() => handleEditTemplate(r)}>编辑</Button>
          <Button size="small" danger icon={<DeleteOutlined />} onClick={() => handleDelete(r)}>删除</Button>
        </Space>
      ),
    },
  ]

  const totalAmount = contracts.filter(c => c.status === 'active').reduce((s: number, c: any) => s + (c.amount || 0), 0)
  const totalMonthly = contracts.filter(c => c.status === 'active').reduce((s: number, c: any) => s + (c.monthly_revenue || 0), 0)

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <h2><FileTextOutlined /> 合同管理</h2>
        {!isClient && (
          <Space>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => { form.resetFields(); setSelected(null); setCreateOpen(true) }}>
              新增合同
            </Button>
            <Button icon={<PlusOutlined />} onClick={handleAddTemplate}>新增模板</Button>
          </Space>
        )}
      </div>

      {/* 已签合同统计卡片 */}
      {/* 已签合同统计卡片 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}><Card size="small"><Statistic title="生效合同" value={contracts.filter(c => c.status === 'active').length} suffix="份" /></Card></Col>
        <Col span={6}><Card size="small"><Statistic title="合同总额" value={totalAmount} precision={0} prefix="¥" /></Card></Col>
        <Col span={6}><Card size="small"><Statistic title="月均收入确认" value={totalMonthly} precision={0} prefix="¥" valueStyle={{ color: '#16a34a' }} /></Card></Col>
        <Col span={6}>
          <Card size="small" style={{ borderColor: expiringCount > 0 ? '#dc2626' : undefined }}>
            <Statistic title={<Space><WarningOutlined style={{ color: expiringCount > 0 ? '#dc2626' : '#94a3b8' }} />即将到期</Space>}
              value={expiringCount} suffix="份" valueStyle={{ color: expiringCount > 0 ? '#dc2626' : '#64748b' }} />
          </Card>
        </Col>
      </Row>

      {/* 合同列表 Tabs */}
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={[
          {
            key: 'contracts',
            label: `已签合同 (${contracts.length})`,
            children: loading ? (
              <SkeletonTable rows={5} columns={8} />
            ) : contracts.length === 0 ? (
              <EmptyState
                title="暂无已签合同"
                description="手动新增合同，或从合同模板快速创建"
                icon={<FileTextOutlined style={{ fontSize: 64, color: '#d9d9d9' }} />}
                {...(!isClient && {
                  actionLabel: '新增合同',
                  onAction: () => { form.resetFields(); setCreateOpen(true) },
                })}
              />
            ) : (
              <Table dataSource={contracts} columns={signedColumns} rowKey="id" pagination={false} scroll={{ x: 1600 }} />
            ),
          },
          {
            key: 'templates',
            label: `合同模板 (${templates.length})`,
            children: templates.length === 0 ? (
              <EmptyState
                title="暂无合同模板"
                description={isClient ? '' : '创建标准化合同模板，快速生成已签合同'}
                icon={<FileTextOutlined style={{ fontSize: 64, color: '#d9d9d9' }} />}
                {...(!isClient && {
                  actionLabel: '新增模板',
                  onAction: handleAddTemplate,
                })}
              />
            ) : (
              <>
                <div style={{ marginBottom: 12, padding: '8px 12px', background: '#f0f7ff', borderRadius: 6, border: '1px solid #bfdbfe' }}>
                  <Text style={{ fontSize: 12, color: '#2563eb' }}>
                    <FileAddOutlined /> 点击「创建合同」从模板生成已签合同，填写对方单位 + 日期即可
                  </Text>
                </div>
                <Table dataSource={templates} columns={templateColumns} rowKey="id" pagination={false} />
              </>
            ),
          },
        ]}
      />

      {/* ===== 新增/从模板创建合同弹窗 ===== */}
      <Modal
        title={selected?.id && !selected?.is_template ? '编辑合同' : selected?.is_template ? `从模板创建：「${selected?.contract_name}」` : '新增合同'}
        open={createOpen}
        onOk={handleCreate}
        onCancel={() => { setCreateOpen(false); setSelected(null) }}
        width={600}
      >
        <Form form={form} layout="vertical">
          <Form.Item label="合同名称" name="contract_name" rules={[{ required: true }]}><Input /></Form.Item>
          <Space size={12}>
            <Form.Item label="合同类型" name="contract_type" rules={[{ required: true }]}><Select options={TYPE_OPTIONS} style={{ width: 140 }} /></Form.Item>
            <Form.Item label="对方单位" name="counterparty" rules={[{ required: true }]}><Input placeholder="签约对方全称" style={{ width: 240 }} /></Form.Item>
          </Space>
          <Space size={12}>
            <Form.Item label="合同金额" name="amount" rules={[{ required: true }]}><InputNumber precision={2} style={{ width: 180 }} prefix="¥" /></Form.Item>
            <Form.Item label="月均确认收入" name="monthly_revenue"><InputNumber precision={2} style={{ width: 180 }} prefix="¥" /></Form.Item>
            <Form.Item label="收入确认周期" name="revenue_period"><Select style={{ width: 120 }} options={[{ label: '按月', value: 'monthly' }, { label: '按季', value: 'quarterly' }, { label: '一次性', value: 'once' }]} /></Form.Item>
          </Space>
          <Form.Item label="合同期间" name="date_range" rules={[{ required: true }]}><DatePicker.RangePicker style={{ width: '100%' }} /></Form.Item>
          <Form.Item label="付款条款" name="payment_terms"><Input.TextArea rows={2} /></Form.Item>
          <Form.Item label="备注" name="remark"><Input.TextArea rows={2} /></Form.Item>
        </Form>
      </Modal>

      {/* ===== 编辑合同弹窗 ===== */}
      <Modal title="编辑合同" open={editOpen} onOk={handleEditSave} onCancel={() => setEditOpen(false)} width={600}>
        <Form form={editForm} layout="vertical">
          <Form.Item label="合同名称" name="contract_name" rules={[{ required: true }]}><Input /></Form.Item>
          <Space size={12}>
            <Form.Item label="合同类型" name="contract_type"><Select options={TYPE_OPTIONS} style={{ width: 140 }} /></Form.Item>
            <Form.Item label="对方单位" name="counterparty"><Input style={{ width: 240 }} /></Form.Item>
          </Space>
          <Space size={12}>
            <Form.Item label="合同金额" name="amount"><InputNumber precision={2} style={{ width: 180 }} /></Form.Item>
            <Form.Item label="月均确认收入" name="monthly_revenue"><InputNumber precision={2} style={{ width: 180 }} /></Form.Item>
            <Form.Item label="收入确认周期" name="revenue_period"><Select style={{ width: 120 }} options={[{ label: '按月', value: 'monthly' }, { label: '按季', value: 'quarterly' }, { label: '一次性', value: 'once' }]} /></Form.Item>
          </Space>
          <Form.Item label="合同期间" name="date_range"><DatePicker.RangePicker style={{ width: '100%' }} /></Form.Item>
          <Form.Item label="付款条款" name="payment_terms"><Input.TextArea rows={2} /></Form.Item>
          <Form.Item label="状态" name="status"><Select options={STATUS_OPTIONS} /></Form.Item>
          <Form.Item label="备注" name="remark"><Input.TextArea rows={2} /></Form.Item>
        </Form>
      </Modal>

      {/* ===== 模板编辑弹窗 ===== */}
      <Modal
        title={selected?.is_template ? '编辑合同模板' : '新增合同模板'}
        open={tplEditOpen}
        onOk={handleSaveTemplate}
        onCancel={() => { setTplEditOpen(false); setSelected(null) }}
        width={600}
      >
        <Form form={tplForm} layout="vertical">
          <Form.Item label="模板名称" name="contract_name" rules={[{ required: true }]}>
            <Input placeholder="如：财税代理服务合同" />
          </Form.Item>
          <Space size={12}>
            <Form.Item label="合同类型" name="contract_type"><Select options={TYPE_OPTIONS} style={{ width: 140 }} /></Form.Item>
            <Form.Item label="对方称呼" name="counterparty"><Input placeholder="如：甲方（委托方）" style={{ width: 240 }} /></Form.Item>
          </Space>
          <Space size={12}>
            <Form.Item label="默认金额" name="amount"><InputNumber precision={2} style={{ width: 180 }} prefix="¥" /></Form.Item>
            <Form.Item label="默认月均收入" name="monthly_revenue"><InputNumber precision={2} style={{ width: 180 }} prefix="¥" /></Form.Item>
            <Form.Item label="收入确认周期" name="revenue_period"><Select style={{ width: 120 }} options={[{ label: '按月', value: 'monthly' }, { label: '按季', value: 'quarterly' }, { label: '一次性', value: 'once' }]} /></Form.Item>
          </Space>
          <Form.Item label="默认付款条款" name="payment_terms"><Input.TextArea rows={2} placeholder="如：按年支付，签约后7日内付清" /></Form.Item>
          <Form.Item label="备注说明" name="remark"><Input.TextArea rows={2} placeholder="模板用途说明" /></Form.Item>
        </Form>
      </Modal>

      {/* ===== 电子签发送弹窗 ===== */}
      <Modal
        title={<Space><SafetyCertificateOutlined />发起电子签 — {selected?.contract_name}</Space>}
        open={esignOpen}
        onOk={handleSendEsign}
        onCancel={() => setEsignOpen(false)}
        okText="发送签署链接"
        confirmLoading={esignSending}
        width={560}
      >
        <div style={{ marginBottom: 16, padding: '10px 14px', background: '#f0f7ff', borderRadius: 6, border: '1px solid #bfdbfe', fontSize: 13, color: '#2563eb' }}>
          选择电子签平台后，系统将生成签署链接并以消息通知方式发送给客户。客户点击链接即可在线完成签署。
        </div>
        <Form form={esignForm} layout="vertical">
          <Form.Item label="电子签平台" name="platform" rules={[{ required: true, message: '请选择电子签平台' }]}>
            <Select
              placeholder="选择电子签服务商"
              options={ESIGN_PLATFORMS.map(p => ({
                label: <span>{p.label} <Text type="secondary" style={{ fontSize: 12 }}>— {p.desc}</Text></span>,
                value: p.value,
              }))}
            />
          </Form.Item>
          <Space size={12} style={{ width: '100%' }}>
            <Form.Item label="签署人姓名" name="signer_name" rules={[{ required: true, message: '请输入签署人姓名' }]} style={{ flex: 1 }}>
              <Input placeholder="对方签署人姓名" />
            </Form.Item>
            <Form.Item label="签署人手机号" name="signer_phone" rules={[
              { required: true, message: '请输入手机号' },
              { pattern: /^1[3-9]\d{9}$/, message: '手机号格式不正确' },
            ]} style={{ flex: 1 }}>
              <Input placeholder="接收签署短信的手机号" maxLength={11} />
            </Form.Item>
          </Space>
        </Form>
      </Modal>

      {/* ===== 电子签发送结果弹窗 ===== */}
      <Modal
        title={<Space><SafetyCertificateOutlined style={{ color: '#16a34a' }} />电子签已发起</Space>}
        open={esignResultOpen}
        onCancel={() => setEsignResultOpen(false)}
        footer={[
          <Button key="close" onClick={() => setEsignResultOpen(false)}>关闭</Button>,
          <Button key="copy" type="primary" icon={<CopyOutlined />} onClick={copySignLink}>复制签署链接</Button>,
        ]}
        width={560}
      >
        {esignResult && (
          <div>
            <div style={{ padding: '16px 0', textAlign: 'center' }}>
              <Tag color="blue" style={{ fontSize: 14, padding: '4px 12px' }}>
                {esignResult.platform_name} · 已发送
              </Tag>
            </div>
            <Descriptions bordered size="small" column={1}>
              <Descriptions.Item label="签署人">{esignResult.signer_name} ({esignResult.signer_phone})</Descriptions.Item>
              <Descriptions.Item label="电子签平台">{esignResult.platform_name}</Descriptions.Item>
              <Descriptions.Item label="签署链接">
                <Space>
                  <Text copyable style={{ fontSize: 12, wordBreak: 'break-all' }}>
                    {window.location.origin}{esignResult.sign_link}
                  </Text>
                </Space>
              </Descriptions.Item>
            </Descriptions>
            <div style={{ marginTop: 16, padding: '10px 14px', background: '#fefce8', borderRadius: 6, border: '1px solid #fde68a', fontSize: 12, color: '#92400e' }}>
              签署链接已通过消息通知发送给客户。客户点击链接即可跳转至 {esignResult.platform_name} 平台完成在线签署。
            </div>
          </div>
        )}
      </Modal>

      {/* ===== 电子签操作记录弹窗 ===== */}
      <Modal title={`电子签记录 — ${selected?.contract_name || ''}`} open={esignLogOpen} onCancel={() => setEsignLogOpen(false)} footer={null} width={650}>
        <Table dataSource={esignLogs} columns={[
          { title: '时间', dataIndex: 'created_at', width: 170, render: (v: string) => v?.slice(0, 19) },
          {
            title: '操作', dataIndex: 'action', width: 130,
            render: (a: string) => {
              const m: Record<string, { color: string; text: string }> = {
                esign_sent: { color: 'blue', text: '发起签署' },
                esign_status_updated: { color: 'green', text: '状态变更' },
              }
              const info = m[a] || { color: 'default', text: a }
              return <Tag color={info.color}>{info.text}</Tag>
            },
          },
          { title: '操作人', dataIndex: 'operator', width: 100 },
          { title: '详情', dataIndex: 'detail', ellipsis: true, render: (d: any) => typeof d === 'string' ? d : JSON.stringify(d || '').substring(0, 200) },
        ]} rowKey="id" size="small" pagination={false} locale={{ emptyText: '暂无签署记录' }} />
      </Modal>
    </div>
  )
}
