import { useState, useEffect } from 'react'
import { Card, Table, Button, Space, Tag, Modal, Form, Input, Select, InputNumber, DatePicker, App, Row, Col, Statistic, Typography } from 'antd'
import { PlusOutlined, EditOutlined, DeleteOutlined, ToolOutlined, BankOutlined, InboxOutlined } from '@ant-design/icons'
import { fixedAssetApi } from '@/services/api'
import { useClient } from '@/contexts/ClientContext'
import SkeletonTable from '@/components/SkeletonTable'
import EmptyState from '@/components/EmptyState'
import dayjs from 'dayjs'

const { Text } = Typography

const CATEGORY_OPTIONS = [
  { label: '房屋建筑物', value: 'building' },
  { label: '电子设备', value: 'electronics' },
  { label: '运输工具', value: 'vehicle' },
  { label: '办公家具', value: 'furniture' },
  { label: '机器设备', value: 'machinery' },
  { label: '其他', value: 'other' },
]

export default function FixedAssets() {
  const [assets, setAssets] = useState<any[]>([])
  const [summary, setSummary] = useState<any>({})
  const [loading, setLoading] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [editOpen, setEditOpen] = useState(false)
  const [selected, setSelected] = useState<any>(null)
  const [depLoading, setDepLoading] = useState(false)
  const [form] = Form.useForm()
  const [editForm] = Form.useForm()
  const { currentClientId } = useClient()
  const { message } = App.useApp()

  const fetchAssets = async () => {
    if (!currentClientId) return
    setLoading(true)
    try {
      const res: any = await fixedAssetApi.list({ client_id: currentClientId })
      setAssets(res.items || [])
      setSummary(res.summary || {})
    } catch { message.error('加载资产列表失败') }
    setLoading(false)
  }

  useEffect(() => { fetchAssets() }, [currentClientId])

  const handleCreate = async () => {
    const values = await form.validateFields()
    try {
      const res: any = await fixedAssetApi.create({ ...values, client_id: currentClientId })
      message.success(res.message || '资产已创建')
      setCreateOpen(false); form.resetFields(); fetchAssets()
    } catch (e: any) { message.error(e?.response?.data?.detail || '创建失败') }
  }

  const handleEdit = (record: any) => {
    setSelected(record)
    editForm.setFieldsValue({
      asset_name: record.asset_name, category: record.category, asset_code: record.asset_code,
      purchase_date: record.purchase_date ? dayjs(record.purchase_date) : null,
      original_value: record.original_value, residual_rate: record.residual_rate,
      useful_life: record.useful_life, location: record.location, remark: record.remark,
      status: record.status,
    })
    setEditOpen(true)
  }

  const handleEditSave = async () => {
    const values = await editForm.validateFields()
    try {
      await fixedAssetApi.update(selected.id, { ...values, purchase_date: values.purchase_date?.format('YYYY-MM-DD') })
      message.success('资产已更新')
      setEditOpen(false); fetchAssets()
    } catch (e: any) { message.error(e?.response?.data?.detail || '更新失败') }
  }

  const handleDelete = async (record: any) => {
    Modal.confirm({
      title: '确认删除', content: `删除资产: ${record.asset_name}?`,
      onOk: async () => {
        try { await fixedAssetApi.delete(record.id); message.success('已删除'); fetchAssets() }
        catch { message.error('删除失败') }
      },
    })
  }

  const handleRunDepreciation = async () => {
    if (!currentClientId) return
    setDepLoading(true)
    try {
      const res: any = await fixedAssetApi.runDepreciation(currentClientId)
      if (res.vouchers_created > 0) {
        message.success(res.message)
      } else {
        message.info(res.message)
      }
      fetchAssets()
    } catch (e: any) { message.error(e?.response?.data?.detail || '折旧失败') }
    setDepLoading(false)
  }

  const columns = [
    { title: '资产编码', dataIndex: 'asset_code', width: 120 },
    { title: '名称', dataIndex: 'asset_name', width: 150 },
    { title: '类别', dataIndex: 'category', width: 100, render: (c: string) => <Tag>{CATEGORY_OPTIONS.find(o => o.value === c)?.label || c}</Tag> },
    { title: '购置日期', dataIndex: 'purchase_date', width: 110 },
    { title: '原值', dataIndex: 'original_value', width: 120, align: 'right' as const, render: (v: number) => `¥${v.toLocaleString()}` },
    { title: '月折旧额', dataIndex: 'monthly_depreciation', width: 110, align: 'right' as const, render: (v: number) => `¥${v.toLocaleString()}` },
    { title: '累计折旧', dataIndex: 'accumulated_depreciation', width: 120, align: 'right' as const, render: (v: number) => `¥${v.toLocaleString()}` },
    { title: '净值', dataIndex: 'net_value', width: 120, align: 'right' as const, render: (v: number) => <Text strong style={{ color: v > 0 ? '#16a34a' : '#dc2626' }}>¥{v.toLocaleString()}</Text> },
    { title: '状态', dataIndex: 'status', width: 80,
      render: (s: string) => <Tag color={s === 'in_use' ? 'green' : s === 'idle' ? 'orange' : 'default'}>{s === 'in_use' ? '在用' : s === 'idle' ? '闲置' : '已处置'}</Tag> },
    {
      title: '操作', width: 180,
      render: (_: any, r: any) => (
        <Space size={0}>
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => handleEdit(r)}>编辑</Button>
          <Button type="link" size="small" danger icon={<DeleteOutlined />} onClick={() => handleDelete(r)}>删除</Button>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 24 }}>
        <h2><BankOutlined /> 固定资产</h2>
        <Space>
          <Button icon={<ToolOutlined />} loading={depLoading} onClick={handleRunDepreciation}
            style={{ color: '#d97706', borderColor: '#d97706' }}>
            计提本月折旧
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => { form.resetFields(); setCreateOpen(true) }}>新增资产</Button>
        </Space>
      </div>

      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}><Card size="small"><Statistic title="资产总数" value={summary.count || 0} suffix="项" /></Card></Col>
        <Col span={6}><Card size="small"><Statistic title="资产原值合计" value={summary.total_original || 0} precision={0} prefix="¥" /></Card></Col>
        <Col span={6}><Card size="small"><Statistic title="累计折旧" value={summary.total_depreciation || 0} precision={0} prefix="¥" valueStyle={{ color: '#d97706' }} /></Card></Col>
        <Col span={6}><Card size="small"><Statistic title="净值合计" value={summary.total_net || 0} precision={0} prefix="¥" valueStyle={{ color: '#16a34a' }} /></Card></Col>
      </Row>

      {loading ? (
        <SkeletonTable rows={5} columns={8} />
      ) : assets.length === 0 ? (
        <Card><EmptyState title="暂无固定资产" description="添加第一个固定资产" actionLabel="新增资产" onAction={() => { form.resetFields(); setCreateOpen(true) }}
          icon={<BankOutlined style={{ fontSize: 64, color: '#d9d9d9' }} />} /></Card>
      ) : (
        <Card style={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
          <Table dataSource={assets} columns={columns} rowKey="id" pagination={false} scroll={{ x: 1200 }} />
        </Card>
      )}

      <Modal title="新增固定资产" open={createOpen} onOk={handleCreate} onCancel={() => setCreateOpen(false)} width={560}>
        <Form form={form} layout="vertical">
          <Form.Item label="资产名称" name="asset_name" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item label="资产编码" name="asset_code"><Input placeholder="自动生成" /></Form.Item>
          <Space size={12}>
            <Form.Item label="类别" name="category" rules={[{ required: true }]}><Select options={CATEGORY_OPTIONS} style={{ width: 160 }} /></Form.Item>
            <Form.Item label="购置日期" name="purchase_date" rules={[{ required: true }]}><DatePicker /></Form.Item>
          </Space>
          <Space size={12}>
            <Form.Item label="原值" name="original_value" rules={[{ required: true }]}><InputNumber precision={2} style={{ width: 160 }} prefix="¥" /></Form.Item>
            <Form.Item label="残值率%" name="residual_rate"><InputNumber precision={1} style={{ width: 100 }} min={0} max={20} /></Form.Item>
            <Form.Item label="使用年限(月)" name="useful_life"><InputNumber style={{ width: 120 }} min={1} /></Form.Item>
          </Space>
          <Form.Item label="存放地点" name="location"><Input /></Form.Item>
          <Form.Item label="状态" name="status"><Select options={[{ label: '在用', value: 'in_use' }, { label: '闲置', value: 'idle' }, { label: '已处置', value: 'disposed' }]} /></Form.Item>
          <Form.Item label="备注" name="remark"><Input.TextArea rows={2} /></Form.Item>
        </Form>
      </Modal>

      <Modal title="编辑固定资产" open={editOpen} onOk={handleEditSave} onCancel={() => setEditOpen(false)} width={560}>
        <Form form={editForm} layout="vertical">
          <Form.Item label="资产名称" name="asset_name" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item label="资产编码" name="asset_code"><Input /></Form.Item>
          <Space size={12}>
            <Form.Item label="类别" name="category"><Select options={CATEGORY_OPTIONS} style={{ width: 160 }} /></Form.Item>
            <Form.Item label="购置日期" name="purchase_date"><DatePicker /></Form.Item>
          </Space>
          <Space size={12}>
            <Form.Item label="原值" name="original_value"><InputNumber precision={2} style={{ width: 160 }} /></Form.Item>
            <Form.Item label="残值率%" name="residual_rate"><InputNumber precision={1} style={{ width: 100 }} /></Form.Item>
            <Form.Item label="使用年限(月)" name="useful_life"><InputNumber style={{ width: 120 }} min={1} /></Form.Item>
          </Space>
          <Form.Item label="存放地点" name="location"><Input /></Form.Item>
          <Form.Item label="状态" name="status"><Select options={[{ label: '在用', value: 'in_use' }, { label: '闲置', value: 'idle' }, { label: '已处置', value: 'disposed' }]} /></Form.Item>
          <Form.Item label="备注" name="remark"><Input.TextArea rows={2} /></Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
