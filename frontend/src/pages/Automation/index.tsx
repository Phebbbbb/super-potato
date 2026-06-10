import { useState, useEffect, useCallback } from 'react'
import { Card, Tabs, Table, Button, Space, Modal, Form, Input, Select, InputNumber, App, Tag, Switch, Descriptions, Empty, Popconfirm } from 'antd'
import { PlusOutlined, MailOutlined, FolderOpenOutlined, DeleteOutlined, ReloadOutlined, PlayCircleOutlined } from '@ant-design/icons'
import { automationApi } from '@/services/api'
import { useClient } from '@/contexts/ClientContext'

export default function Automation() {
  const { message } = App.useApp()
  const { clientList } = useClient()
  const [activeTab, setActiveTab] = useState('hot-folders')

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h2 style={{ margin: 0 }}>自动化采集</h2>
        <span style={{ color: '#94a3b8', fontSize: 13 }}>热文件夹 · 邮件轮询 · 通道状态</span>
      </div>

      <Tabs activeKey={activeTab} onChange={setActiveTab} items={[
        { key: 'hot-folders', label: '热文件夹', children: <HotFolders /> },
        { key: 'email', label: '邮件采集', children: <EmailCollectors /> },
        { key: 'status', label: '通道状态', children: <StatusOverview /> },
      ]} />
    </div>
  )
}

function HotFolders() {
  const [items, setItems] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)
  const [form] = Form.useForm()
  const { message } = App.useApp()
  const { clientList } = useClient()

  const fetch = useCallback(async () => {
    setLoading(true)
    try { const res: any = await automationApi.hotFolders(); setItems(res.items || res.watchers || []) } catch { /* */ }
    setLoading(false)
  }, [])

  useEffect(() => { fetch() }, [fetch])

  const handleAdd = async () => {
    const values = await form.validateFields()
    await automationApi.addHotFolder(values)
    message.success('已添加')
    setOpen(false); form.resetFields(); fetch()
  }

  const handleDelete = async (id: string) => {
    await automationApi.removeHotFolder(id)
    message.success('已移除')
    fetch()
  }

  const handleToggle = async (id: string, enabled: boolean) => {
    await automationApi.toggleHotFolder(id, enabled)
    fetch()
  }

  return (
    <>
      <Space style={{ marginBottom: 16 }}>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>添加监控目录</Button>
        <Button icon={<ReloadOutlined />} onClick={fetch}>刷新</Button>
      </Space>
      <Table dataSource={items} rowKey="id" loading={loading} size="small" pagination={false}
        locale={{ emptyText: '暂无热文件夹监控，请添加需监控的文件夹路径' }}
        columns={[
          { title: '目录路径', dataIndex: 'path', ellipsis: true },
          { title: '标签', dataIndex: 'label', width: 120 },
          { title: '客户', dataIndex: 'client_id', width: 120, render: (v: string) => clientList.find(c => c.id === v)?.name || v?.slice(0, 8) || '-' },
          { title: '来源', dataIndex: 'source', width: 100, render: (v: string) => v === 'scanner' ? '扫描仪' : '文件夹' },
          { title: '状态', dataIndex: 'enabled', width: 80,
            render: (v: boolean, r: any) => <Switch checked={v !== false} size="small" onChange={(en) => handleToggle(r.id, en)} /> },
          { title: '操作', width: 80,
            render: (_: any, r: any) => (
              <Popconfirm title="确定移除？" onConfirm={() => handleDelete(r.id)}>
                <Button type="link" danger size="small" icon={<DeleteOutlined />} />
              </Popconfirm>
            )},
        ]} />
      <Modal title="添加热文件夹监控" open={open} onOk={handleAdd} onCancel={() => { setOpen(false); form.resetFields() }}>
        <Form form={form} layout="vertical">
          <Form.Item name="path" label="目录路径" rules={[{ required: true }]}><Input placeholder="如 /data/invoices/" /></Form.Item>
          <Form.Item name="client_id" label="归属客户" rules={[{ required: true }]}>
            <Select options={clientList.map(c => ({ label: c.name, value: c.id }))} />
          </Form.Item>
          <Form.Item name="label" label="标签"><Input placeholder="如 进项发票目录" /></Form.Item>
          <Form.Item name="source" label="来源类型" initialValue="hot_folder">
            <Select options={[{ label: '文件夹监控', value: 'hot_folder' }, { label: '扫描仪', value: 'scanner' }]} />
          </Form.Item>
        </Form>
      </Modal>
    </>
  )
}

function EmailCollectors() {
  const [items, setItems] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)
  const [form] = Form.useForm()
  const { message } = App.useApp()
  const { clientList } = useClient()

  const fetch = useCallback(async () => {
    setLoading(true)
    try { const res: any = await automationApi.emailCollectors(); setItems(res.collectors || res.items || []) } catch { /* */ }
    setLoading(false)
  }, [])

  useEffect(() => { fetch() }, [fetch])

  const handleAdd = async () => {
    const values = await form.validateFields()
    await automationApi.addEmailCollector(values)
    message.success('已添加')
    setOpen(false); form.resetFields(); fetch()
  }

  const handleDelete = async (id: string) => {
    await automationApi.removeEmailCollector(id)
    message.success('已移除')
    fetch()
  }

  const handleToggle = async (id: string, enabled: boolean) => {
    await automationApi.toggleEmailCollector(id, enabled)
    fetch()
  }

  const handleTest = async (id: string) => {
    try {
      const res: any = await automationApi.testEmailCollector(id)
      message.success(res.message || '测试完成')
    } catch { message.error('测试失败') }
  }

  return (
    <>
      <Space style={{ marginBottom: 16 }}>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>添加邮件采集器</Button>
        <Button icon={<ReloadOutlined />} onClick={fetch}>刷新</Button>
      </Space>
      <Table dataSource={items} rowKey="id" loading={loading} size="small" pagination={false}
        locale={{ emptyText: '暂无邮件采集器，请添加 IMAP 邮箱配置' }}
        columns={[
          { title: '邮箱', dataIndex: 'imap_user', width: 200 },
          { title: 'IMAP服务器', dataIndex: 'imap_host', width: 180 },
          { title: '文件夹', dataIndex: 'folder', width: 100 },
          { title: '间隔(分钟)', dataIndex: 'interval_minutes', width: 100 },
          { title: '客户', dataIndex: 'client_id', width: 120, render: (v: string) => clientList.find(c => c.id === v)?.name || v?.slice(0, 8) || '-' },
          { title: '状态', dataIndex: 'enabled', width: 80,
            render: (v: boolean, r: any) => <Switch checked={v !== false} size="small" onChange={(en) => handleToggle(r.id, en)} /> },
          { title: '操作', width: 140,
            render: (_: any, r: any) => (
              <Space size={0}>
                <Button type="link" size="small" icon={<PlayCircleOutlined />} onClick={() => handleTest(r.id)}>测试</Button>
                <Popconfirm title="确定移除？" onConfirm={() => handleDelete(r.id)}>
                  <Button type="link" danger size="small" icon={<DeleteOutlined />} />
                </Popconfirm>
              </Space>
            )},
        ]} />
      <Modal title="添加邮件采集器" open={open} onOk={handleAdd} onCancel={() => { setOpen(false); form.resetFields() }} width={480}>
        <Form form={form} layout="vertical">
          <Form.Item name="client_id" label="归属客户" rules={[{ required: true }]}>
            <Select options={clientList.map(c => ({ label: c.name, value: c.id }))} />
          </Form.Item>
          <Form.Item name="imap_host" label="IMAP 服务器" rules={[{ required: true }]}><Input placeholder="如 imap.qq.com" /></Form.Item>
          <Form.Item name="imap_user" label="邮箱地址" rules={[{ required: true }]}><Input placeholder="如 invoice@company.com" /></Form.Item>
          <Form.Item name="imap_pass" label="邮箱密码/授权码" rules={[{ required: true }]}><Input.Password /></Form.Item>
          <Form.Item name="folder" label="监控文件夹" initialValue="INBOX"><Input /></Form.Item>
          <Form.Item name="interval_minutes" label="轮询间隔(分钟)" initialValue={5}><InputNumber min={1} max={60} /></Form.Item>
        </Form>
      </Modal>
    </>
  )
}

function StatusOverview() {
  const [status, setStatus] = useState<any>(null)
  const [loading, setLoading] = useState(false)

  const fetch = async () => {
    setLoading(true)
    try { const res: any = await automationApi.status(); setStatus(res) } catch { /* */ }
    setLoading(false)
  }

  useEffect(() => { fetch() }, [])

  return (
    <div>
      <Button icon={<ReloadOutlined />} loading={loading} onClick={fetch} style={{ marginBottom: 16 }}>刷新状态</Button>
      {status && (
        <Card>
          <Descriptions column={2} bordered size="small">
            <Descriptions.Item label="热文件夹">
              <Tag color={status.hot_folders?.running ? 'green' : 'red'}>{status.hot_folders?.running ? '运行中' : '已停止'}</Tag>
              {' '}{status.hot_folders?.count}/{status.hot_folders?.total} 活跃
            </Descriptions.Item>
            <Descriptions.Item label="邮件采集">
              <Tag color={status.email_collectors?.running ? 'green' : 'red'}>{status.email_collectors?.running ? '运行中' : '已停止'}</Tag>
              {' '}{status.email_collectors?.count}/{status.email_collectors?.total} 活跃
            </Descriptions.Item>
            <Descriptions.Item label="Webhook">
              {status.webhooks?.active}/{status.webhooks?.total} 活跃
            </Descriptions.Item>
            <Descriptions.Item label="ZIP导入">{status.zip_import?.enabled ? '可用' : '不可用'}</Descriptions.Item>
          </Descriptions>
        </Card>
      )}
    </div>
  )
}
