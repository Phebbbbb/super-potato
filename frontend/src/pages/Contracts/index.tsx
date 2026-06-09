import { useState, useEffect } from 'react'
import { Card, Table, Button, Space, Tag, Modal, Form, Input, Select, InputNumber, DatePicker, App, Row, Col, Statistic, Typography, Badge } from 'antd'
import { PlusOutlined, EditOutlined, DeleteOutlined, FileTextOutlined, WarningOutlined, InboxOutlined } from '@ant-design/icons'
import { contractApi } from '@/services/api'
import { useClient } from '@/contexts/ClientContext'
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

export default function Contracts() {
  const [contracts, setContracts] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [editOpen, setEditOpen] = useState(false)
  const [selected, setSelected] = useState<any>(null)
  const [expiringCount, setExpiringCount] = useState(0)
  const [form] = Form.useForm()
  const [editForm] = Form.useForm()
  const { currentClientId } = useClient()
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

  useEffect(() => { fetchContracts() }, [currentClientId])

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
        try { await contractApi.delete(record.id); message.success('已删除'); fetchContracts() }
        catch { message.error('删除失败') }
      },
    })
  }

  const columns = [
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
    { title: '月均确认收入', dataIndex: 'monthly_revenue', width: 120, align: 'right' as const, render: (v: number) => v ? `¥${v.toLocaleString()}` : '-' },
    {
      title: '操作', width: 160,
      render: (_: any, r: any) => (
        <Space size={0}>
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => handleEdit(r)}>编辑</Button>
          <Button type="link" size="small" danger icon={<DeleteOutlined />} onClick={() => handleDelete(r)}>删除</Button>
        </Space>
      ),
    },
  ]

  const totalAmount = contracts.filter(c => c.status === 'active').reduce((s: number, c: any) => s + (c.amount || 0), 0)
  const totalMonthly = contracts.filter(c => c.status === 'active').reduce((s: number, c: any) => s + (c.monthly_revenue || 0), 0)

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 24 }}>
        <h2><FileTextOutlined /> 合同管理</h2>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => { form.resetFields(); setCreateOpen(true) }}>新增合同</Button>
      </div>

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

      {loading ? (
        <SkeletonTable rows={5} columns={8} />
      ) : contracts.length === 0 ? (
        <Card><EmptyState title="暂无合同" description="添加第一个合同" actionLabel="新增合同" onAction={() => { form.resetFields(); setCreateOpen(true) }}
          icon={<FileTextOutlined style={{ fontSize: 64, color: '#d9d9d9' }} />} /></Card>
      ) : (
        <Card style={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
          <Table dataSource={contracts} columns={columns} rowKey="id" pagination={false} scroll={{ x: 1300 }} />
        </Card>
      )}

      <Modal title="新增合同" open={createOpen} onOk={handleCreate} onCancel={() => setCreateOpen(false)} width={600}>
        <Form form={form} layout="vertical">
          <Form.Item label="合同名称" name="contract_name" rules={[{ required: true }]}><Input /></Form.Item>
          <Space size={12}>
            <Form.Item label="合同类型" name="contract_type" rules={[{ required: true }]}><Select options={TYPE_OPTIONS} style={{ width: 140 }} /></Form.Item>
            <Form.Item label="对方单位" name="counterparty" rules={[{ required: true }]}><Input style={{ width: 240 }} /></Form.Item>
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
          <Form.Item label="状态" name="status"><Select options={[{ label: '生效中', value: 'active' }, { label: '已到期', value: 'expired' }, { label: '已终止', value: 'terminated' }, { label: '已完成', value: 'completed' }]} /></Form.Item>
          <Form.Item label="备注" name="remark"><Input.TextArea rows={2} /></Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
