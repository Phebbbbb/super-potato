import { useState, useEffect } from 'react'
import { Card, Table, Button, Space, Modal, Form, Input, Select, DatePicker, Tag, App, Badge, Upload } from 'antd'
import { PlusOutlined, EnvironmentOutlined, CameraOutlined, UploadOutlined, EditOutlined, DeleteOutlined, InboxOutlined } from '@ant-design/icons'
import { fieldTaskApi } from '@/services/api'
import { useClient } from '@/contexts/ClientContext'
import SkeletonTable from '@/components/SkeletonTable'
import EmptyState from '@/components/EmptyState'
import dayjs from 'dayjs'

const TASK_TYPE_MAP: Record<string, string> = {
  tax_bureau: '税务局', business_reg: '工商局', bank: '银行', client_visit: '客户拜访', document_delivery: '文件送达', other: '其他',
}

export default function FieldTasks() {
  const [tasks, setTasks] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [editOpen, setEditOpen] = useState(false)
  const [detailOpen, setDetailOpen] = useState(false)
  const [selected, setSelected] = useState<any>(null)
  const [form] = Form.useForm()
  const [editForm] = Form.useForm()
  const { currentClientId } = useClient()
  const { message } = App.useApp()
  const [capturedImages, setCapturedImages] = useState<Record<string, File>>({})

  const fetchTasks = async () => {
    if (!currentClientId) return
    setLoading(true)
    try {
      const res: any = await fieldTaskApi.list({ client_id: currentClientId })
      setTasks(res.items || [])
    } catch { message.error('加载数据失败') }
    setLoading(false)
  }

  useEffect(() => { fetchTasks() }, [currentClientId])

  const handleCreate = async () => {
    const values = await form.validateFields()
    await fieldTaskApi.create({ ...values, client_id: currentClientId })
    message.success('外勤任务创建成功')
    setCreateOpen(false); form.resetFields(); fetchTasks()
  }

  const handleComplete = async (taskId: string) => {
    await fieldTaskApi.update(taskId, { status: 'completed' })
    message.success('任务已标记完成')
    fetchTasks()
  }

  const handleEdit = (record: any) => {
    setSelected(record)
    editForm.setFieldsValue({
      title: record.title,
      task_type: record.task_type,
      description: record.description,
      priority: record.priority,
      deadline: record.deadline ? dayjs(record.deadline) : null,
    })
    setEditOpen(true)
  }

  const handleEditSave = async () => {
    const values = await editForm.validateFields()
    await fieldTaskApi.update(selected.id, values)
    message.success('任务已更新')
    setEditOpen(false); fetchTasks()
  }

  const handleDelete = async (id: string) => {
    await fieldTaskApi.delete(id)
    message.success('任务已删除')
    fetchTasks()
  }

  const columns = [
    { title: '类型', dataIndex: 'task_type', width: 100, render: (t: string) => <Tag color="blue">{TASK_TYPE_MAP[t] || t}</Tag> },
    { title: '标题', dataIndex: 'title', width: 200 },
    { title: '优先级', dataIndex: 'priority', width: 80, render: (p: string) => <Tag color={p === 'urgent' ? 'red' : p === 'high' ? 'orange' : 'blue'}>{p}</Tag> },
    { title: '状态', dataIndex: 'status', width: 100, render: (s: string) => {
        const m: Record<string, { status: 'success' | 'processing' | 'default' | 'error'; text: string }> = {
          pending: { status: 'default', text: '待分派' }, assigned: { status: 'processing', text: '已分派' },
          in_progress: { status: 'processing', text: '执行中' }, completed: { status: 'success', text: '已完成' }, failed: { status: 'error', text: '失败' },
        }
        return <Badge status={m[s]?.status} text={m[s]?.text || s} />
      }},
    { title: '截止日', dataIndex: 'deadline', width: 110 },
    { title: '操作', key: 'act', width: 260, render: (_: any, r: any) => (
        <Space>
          <Button type="link" size="small" onClick={() => { setSelected(r); setDetailOpen(true) }}>详情</Button>
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => handleEdit(r)}>编辑</Button>
          <Button type="link" size="small" icon={<CameraOutlined />}
            style={{ color: capturedImages[r.id] ? '#16a34a' : undefined }}
            onClick={() => {
              const input = document.createElement('input')
              input.type = 'file'; input.accept = 'image/*'; input.capture = 'environment'
              input.onchange = async (e: any) => {
                const file = e.target.files?.[0]
                if (file) {
                  setCapturedImages(prev => ({ ...prev, [r.id]: file }))
                  message.success(`${file.name} 已捕获，完成或更新任务时将上传`)
                }
              }
              input.click()
            }} />
          {capturedImages[r.id] && (
            <Button type="link" size="small" onClick={async () => {
              const file = capturedImages[r.id]
              if (!file) return
              const fd = new FormData()
              fd.append('file', file)
              try {
                await fetch(`/api/documents/upload?client_id=${currentClientId}`, { method: 'POST', body: fd })
                message.success('现场照片已上传至票据中心')
                setCapturedImages(prev => { const n = { ...prev }; delete n[r.id]; return n })
              } catch { message.error('上传失败') }
            }} style={{ color: '#16a34a' }}>上传</Button>
          )}
          {r.status !== 'completed' && <Button type="link" size="small" onClick={() => handleComplete(r.id)}>完成</Button>}
          <Button type="link" size="small" danger icon={<DeleteOutlined />} onClick={() => {
            Modal.confirm({ title: '确认删除?', content: `将删除任务: ${r.title}`, onOk: () => handleDelete(r.id) })
          }} />
        </Space>
      )},
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 24 }}>
        <h2><EnvironmentOutlined /> 外勤任务</h2>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>创建外勤任务</Button>
      </div>

      {loading ? (
        <SkeletonTable rows={5} columns={6} />
      ) : tasks.length === 0 ? (
        <Card>
          <EmptyState
            title="暂无外勤任务"
            description="创建第一个外勤任务"
            actionLabel="创建外勤任务"
            onAction={() => setCreateOpen(true)}
            icon={<EnvironmentOutlined style={{ fontSize: 64, color: '#d9d9d9' }} />}
          />
        </Card>
      ) : (
        <Card style={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
          <Table dataSource={tasks} columns={columns} rowKey="id" pagination={false} />
        </Card>
      )}

      <Modal title="创建外勤任务" open={createOpen} onOk={handleCreate} onCancel={() => setCreateOpen(false)}>
        <Form form={form} layout="vertical">
          <Form.Item label="任务类型" name="task_type" rules={[{ required: true }]}>
            <Select options={[
              { label: '税务局办事', value: 'tax_bureau' }, { label: '工商局办事', value: 'business_reg' },
              { label: '银行办事', value: 'bank' }, { label: '客户拜访', value: 'client_visit' },
              { label: '文件送达', value: 'document_delivery' }, { label: '其他', value: 'other' },
            ]} />
          </Form.Item>
          <Form.Item label="任务标题" name="title" rules={[{ required: true }]}><Input placeholder="如：前往税务局领取发票" /></Form.Item>
          <Form.Item label="任务描述" name="description"><Input.TextArea rows={3} /></Form.Item>
          <Form.Item label="优先级" name="priority"><Select options={[{ label: '普通', value: 'normal' }, { label: '高', value: 'high' }, { label: '紧急', value: 'urgent' }]} /></Form.Item>
          <Form.Item label="截止日期" name="deadline"><DatePicker style={{ width: '100%' }} /></Form.Item>
          <Form.Item label="附件（现场照片）" name="attachments">
            <Upload multiple listType="picture" customRequest={(opt: any) => setTimeout(() => opt.onSuccess?.(), 0)}>
              <Button icon={<UploadOutlined />}>选择照片</Button>
            </Upload>
          </Form.Item>
        </Form>
      </Modal>

      <Modal title="编辑外勤任务" open={editOpen} onOk={handleEditSave} onCancel={() => setEditOpen(false)}>
        <Form form={editForm} layout="vertical">
          <Form.Item label="任务类型" name="task_type" rules={[{ required: true }]}>
            <Select options={[
              { label: '税务局办事', value: 'tax_bureau' }, { label: '工商局办事', value: 'business_reg' },
              { label: '银行办事', value: 'bank' }, { label: '客户拜访', value: 'client_visit' },
              { label: '文件送达', value: 'document_delivery' }, { label: '其他', value: 'other' },
            ]} />
          </Form.Item>
          <Form.Item label="任务标题" name="title" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item label="任务描述" name="description"><Input.TextArea rows={3} /></Form.Item>
          <Form.Item label="优先级" name="priority"><Select options={[{ label: '普通', value: 'normal' }, { label: '高', value: 'high' }, { label: '紧急', value: 'urgent' }]} /></Form.Item>
          <Form.Item label="截止日期" name="deadline"><DatePicker style={{ width: '100%' }} /></Form.Item>
        </Form>
      </Modal>

      <Modal title="任务详情" open={detailOpen} onCancel={() => setDetailOpen(false)} footer={null} width={600}>
        {selected && (
          <div>
            <p><strong>标题：</strong>{selected.title}</p>
            <p><strong>类型：</strong>{TASK_TYPE_MAP[selected.task_type] || selected.task_type}</p>
            <p><strong>描述：</strong>{selected.description || '-'}</p>
            <p><strong>状态：</strong>{selected.status}</p>
            <p><strong>优先级：</strong>{selected.priority}</p>
            <p><strong>截止日：</strong>{selected.deadline || '-'}</p>
            <p><strong>执行记录：</strong>{selected.notes || '-'}</p>
            {selected.attachments?.length > 0 && <p><strong>附件：</strong>{selected.attachments.length} 个文件</p>}
          </div>
        )}
      </Modal>
    </div>
  )
}
