import { useState, useEffect } from 'react'
import { Card, Table, Tag, Button, Space, Modal, Form, Input, Select, App, Typography, Switch, Avatar, Tooltip } from 'antd'
import { PlusOutlined, EditOutlined, InboxOutlined, UserOutlined } from '@ant-design/icons'
import { useClient } from '@/contexts/ClientContext'
import { clientApi } from '@/services/api'
import SkeletonTable from '@/components/SkeletonTable'
import EmptyState from '@/components/EmptyState'

const { Text } = Typography

export default function Clients() {
  const [clients, setClients] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [editOpen, setEditOpen] = useState(false)
  const [editing, setEditing] = useState<any>(null)
  const [staffList, setStaffList] = useState<any[]>([])
  const [form] = Form.useForm()
  const { message } = App.useApp()
  const { switchClient, currentClientId, loadClients } = useClient()

  const fetchClients = async () => {
    setLoading(true)
    try {
      const res: any = await clientApi.list({ page_size: 200 })
      if (res.items) setClients(res.items)
    } catch { message.error('加载客户列表失败') }
    setLoading(false)
  }

  const fetchStaff = async () => {
    try {
      const res: any = await clientApi.availableStaff()
      setStaffList(res || [])
    } catch { /* ignore */ }
  }

  useEffect(() => { fetchClients(); fetchStaff() }, [])

  const handleSave = async () => {
    const values = await form.validateFields()
    try {
      if (editing?.id) {
        await clientApi.update(editing.id, values)
        message.success('客户信息已更新')
      } else {
        await clientApi.create(values)
        message.success('客户创建成功')
      }
      setEditOpen(false)
      fetchClients()
      loadClients()
    } catch { message.error('保存失败') }
  }

  const openEdit = (record?: any) => {
    setEditing(record || null)
    if (record) form.setFieldsValue(record)
    else form.resetFields()
    setEditOpen(true)
  }

  const columns = [
    { title: '公司名称', dataIndex: 'name', key: 'name', width: 200 },
    { title: '税号', dataIndex: 'tax_no', key: 'tax_no', width: 180 },
    {
      title: '纳税人性质', dataIndex: 'taxpayer_type', key: 'taxpayer_type', width: 100,
      render: (t: string) => <Tag color={t === 'general' ? 'blue' : 'green'}>{t === 'general' ? '一般纳税人' : '小规模'}</Tag>,
    },
    { title: '行业', dataIndex: 'industry', key: 'industry', width: 100 },
    { title: '联系人', dataIndex: 'contact_person', key: 'contact_person', width: 80 },
    { title: '电话', dataIndex: 'contact_phone', key: 'contact_phone', width: 120 },
    {
      title: '专属服务', dataIndex: 'assigned_staff_name', key: 'assigned_staff', width: 90,
      render: (name: string, record: any) => name
        ? <Tag icon={<UserOutlined />} color="blue">{name}</Tag>
        : <Tag color="default">未分配</Tag>,
    },
    {
      title: '状态', dataIndex: 'is_active', key: 'is_active', width: 70,
      render: (v: boolean) => <Tag color={v ? 'green' : 'red'}>{v ? '服务中' : '停用'}</Tag>,
    },
    {
      title: '操作', key: 'actions', width: 150,
      render: (_: any, record: any) => (
        <Space>
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => openEdit(record)}>编辑</Button>
          {record.id !== currentClientId && (
            <Button type="link" size="small" onClick={() => { switchClient(record.id); message.success(`已切换到：${record.name}`) }}>
              切换
            </Button>
          )}
          {record.id === currentClientId && <Tag color="blue">当前</Tag>}
          <Button type="link" size="small" danger onClick={async () => {
            try {
              await clientApi.delete(record.id)
              message.success('客户已删除')
              fetchClients(); loadClients()
            } catch { message.error('删除失败') }
          }}>删除</Button>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 24 }}>
        <h2>客户管理</h2>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => openEdit()}>新增客户</Button>
      </div>

      {loading ? (
        <SkeletonTable rows={6} columns={5} />
      ) : clients.length === 0 ? (
        <Card>
          <EmptyState
            title="暂无客户"
            description="新增第一个客户以开始财税管理"
            icon={<InboxOutlined style={{ fontSize: 64, color: '#d9d9d9' }} />}
          />
        </Card>
      ) : (
        <Card style={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
          <Table dataSource={clients} columns={columns} rowKey="id" pagination={false} />
        </Card>
      )}

      <Modal title={editing?.id ? '编辑客户' : '新增客户'} open={editOpen}
        onOk={handleSave} onCancel={() => setEditOpen(false)} okText="保存" width={600}>
        <Form form={form} layout="vertical">
          <Form.Item label="公司名称" name="name" rules={[{ required: true }]}>
            <Input placeholder="客户公司全称" />
          </Form.Item>
          <Form.Item label="统一社会信用代码" name="tax_no" rules={[{ required: true }]}>
            <Input placeholder="18位信用代码" />
          </Form.Item>
          <Form.Item label="纳税人性质" name="taxpayer_type">
            <Select options={[{ label: '一般纳税人', value: 'general' }, { label: '小规模纳税人', value: 'small' }]} />
          </Form.Item>
          <Form.Item label="所属行业" name="industry">
            <Select options={[
              { label: '信息技术', value: 'it' }, { label: '商务服务', value: 'business_service' },
              { label: '批发零售', value: 'retail' }, { label: '制造业', value: 'manufacturing' },
            ]} />
          </Form.Item>
          <Form.Item label="专属服务人员" name="assigned_staff_id" tooltip="每位客户只能分配一位服务人员">
            <Select
              allowClear
              placeholder="选择服务人员（可选）"
              options={staffList.map((s: any) => ({
                label: `${s.display_name}（${s.role === 'admin' ? '管理员' : s.role} · 已服务 ${s.assigned_count} 户）`,
                value: s.id,
              }))}
              onChange={(val) => {
                if (!val) form.setFieldValue('assigned_staff_id', null)
              }}
            />
          </Form.Item>
          <Form.Item label="联系人" name="contact_person"><Input /></Form.Item>
          <Form.Item label="联系电话" name="contact_phone"><Input /></Form.Item>
          <Form.Item label="地址" name="address"><Input /></Form.Item>
          <Form.Item label="备注" name="remark"><Input.TextArea rows={2} /></Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
