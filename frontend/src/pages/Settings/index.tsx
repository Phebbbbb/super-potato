import { useState, useEffect, useRef } from 'react'
import { Card, Table, Form, Input, Select, Button, App, Tag, Typography, Modal, Tooltip, Space, Divider, Switch, Upload, InputNumber } from 'antd'
import { PlusOutlined, SaveOutlined, SearchOutlined, CrownOutlined, ReloadOutlined, CopyOutlined, DeleteOutlined, UploadOutlined, WechatOutlined, DingdingOutlined, QrcodeOutlined, DownloadOutlined } from '@ant-design/icons'
import { accountApi, settingsApi, subscriptionApi, staffApi, interactionApi, automationApi, systemApi, auditApi, userApi, clientApi } from '@/services/api'

const { Text } = Typography

function TaxAutoConfig() {
  const { message } = App.useApp()
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    settingsApi.get('tax_bureau_auth').then((res: any) => {
      if (res?.config_value && Object.keys(res.config_value).length > 0) {
        form.setFieldsValue(res.config_value)
      }
    }).catch(() => {})
  }, [])

  const handleSave = async () => {
    const values = await form.validateFields()
    setLoading(true)
    try {
      await settingsApi.update('tax_bureau_auth', values)
      message.success('电子税务局凭据已保存')
    } catch { message.error('保存失败') }
    setLoading(false)
  }

  return (
    <div style={{ maxWidth: 500 }}>
      <div style={{ marginBottom: 16, padding: 12, background: '#fefce8', borderRadius: 6, border: '1px solid #fde68a' }}>
        <Text style={{ fontSize: 13 }}>
          配置完成后，系统将自动登录电子税务局执行开票和申报操作。
          请确保服务器已安装 Playwright：<Text code>pip install playwright && playwright install chromium</Text>
        </Text>
      </div>
      <Form form={form} layout="vertical">
        <Form.Item label="省份" name="province" rules={[{ required: true, message: '请选择电子税务局省份' }]}>
          <Select placeholder="选择所在省份" options={[
            { label: '北京市', value: 'beijing' },
            { label: '上海市', value: 'shanghai' },
            { label: '广东省', value: 'guangdong' },
            { label: '浙江省', value: 'zhejiang' },
            { label: '江苏省', value: 'jiangsu' },
            { label: '通用（全国）', value: 'generic' },
          ]} />
        </Form.Item>
        <Form.Item label="登录账号（社会信用代码/税号）" name="username" rules={[{ required: true, message: '请输入电子税务局登录账号' }]}>
          <Input placeholder="18位统一社会信用代码" maxLength={30} />
        </Form.Item>
        <Form.Item label="登录密码" name="password" rules={[{ required: true, message: '请输入电子税务局登录密码' }]}>
          <Input.Password placeholder="电子税务局登录密码" maxLength={50} />
        </Form.Item>
        <Button type="primary" icon={<SaveOutlined />} onClick={handleSave} loading={loading}>
          保存凭据
        </Button>
      </Form>
    </div>
  )
}


function StaffUsageTab() {
  const { message } = App.useApp()
  const [staff, setStaff] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [history, setHistory] = useState<any[]>([])
  const [historyVisible, setHistoryVisible] = useState(false)
  const [selectedUser, setSelectedUser] = useState<any>(null)

  const fetchStaff = async () => {
    setLoading(true)
    try {
      const res: any = await staffApi.usage()
      setStaff(res.staff || [])
    } catch { message.error('获取人员状态失败') }
    setLoading(false)
  }

  useEffect(() => { fetchStaff() }, [])

  const showHistory = async (user: any) => {
    setSelectedUser(user)
    try {
      const res: any = await staffApi.loginHistory(user.user_id, 30)
      setHistory(res.history || [])
    } catch { setHistory([]) }
    setHistoryVisible(true)
  }

  const columns = [
    { title: '姓名', dataIndex: 'display_name', key: 'name' },
    { title: '账号', dataIndex: 'username', key: 'username' },
    {
      title: '角色', dataIndex: 'role', key: 'role',
      render: (r: string) => {
        const m: Record<string, { color: string; label: string }> = {
          admin: { color: 'red', label: '管理员' },
          accountant: { color: 'blue', label: '会计' },
          reviewer: { color: 'green', label: '审核员' },
          field_agent: { color: 'orange', label: '外勤' },
          viewer: { color: 'default', label: '查看者' },
        }
        const t = m[r] || { color: 'default', label: r }
        return <Tag color={t.color}>{t.label}</Tag>
      },
    },
    {
      title: '状态', key: 'status',
      render: (_: any, r: any) => (
        <Space size={4}>
          <Tag color={r.is_active ? 'green' : 'red'}>{r.is_active ? '启用' : '禁用'}</Tag>
          {r.account_locked && <Tag color="red">锁定</Tag>}
        </Space>
      ),
    },
    {
      title: '最近登录', dataIndex: 'last_login_at', key: 'last_login',
      render: (v: string | null) => v ? new Date(v).toLocaleString('zh-CN') : <Text type="secondary">从未登录</Text>,
    },
    {
      title: '30天登录次数', dataIndex: 'login_count_30d', key: 'count',
      render: (v: number) => <Tag color={v > 20 ? 'green' : v > 5 ? 'blue' : 'default'}>{v}</Tag>,
    },
    {
      title: '失败尝试', dataIndex: 'failed_attempts', key: 'failed',
      render: (v: number) => v > 0 ? <Tag color="red">{v}</Tag> : <Text type="secondary">0</Text>,
    },
    {
      title: '操作', key: 'actions',
      render: (_: any, r: any) => (
        <Button type="link" size="small" onClick={() => showHistory(r)}>登录记录</Button>
      ),
    },
  ]

  return (
    <div>
      <div style={{ marginBottom: 12, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Text strong style={{ fontSize: 14 }}>服务端人员使用状态</Text>
        <Button size="small" icon={<ReloadOutlined />} loading={loading} onClick={fetchStaff}>刷新</Button>
      </div>
      <Table dataSource={staff} columns={columns} rowKey="user_id" size="small" pagination={false} loading={loading} />

      <Modal title={`${selectedUser?.display_name || ''} — 登录记录`} open={historyVisible}
        onCancel={() => setHistoryVisible(false)} footer={null} width={500}>
        <Table dataSource={history} columns={[
          { title: '登录时间', dataIndex: 'login_at', render: (v: string) => new Date(v).toLocaleString('zh-CN') },
          { title: 'IP', dataIndex: 'ip_address', render: (v: string) => v || '--' },
        ]} rowKey="id" size="small" pagination={false} />
      </Modal>
    </div>
  )
}


function SubscriptionTab() {
  const { message, modal } = App.useApp()
  const [subs, setSubs] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [msgModalOpen, setMsgModalOpen] = useState(false)
  const [msgClient, setMsgClient] = useState<any>(null)
  const [msgForm] = Form.useForm()
  const [msgSending, setMsgSending] = useState(false)

  const fetchSubs = async () => {
    setLoading(true)
    try {
      const res: any = await subscriptionApi.list()
      setSubs(res.subscriptions || [])
    } catch { message.error('获取订阅列表失败') }
    setLoading(false)
  }

  useEffect(() => { fetchSubs() }, [])

  const handleUpgrade = async (clientId: string, phone: string) => {
    Modal.confirm({
      title: '确认升级为 VIP 年费会员？',
      content: `将为客户 ${clientId} 开通 1 年 VIP 会员`,
      onOk: async () => {
        try {
          await subscriptionApi.upgrade(clientId, phone)
          message.success('已升级为 VIP 年费会员')
          fetchSubs()
        } catch { message.error('升级失败') }
      },
    })
  }

  const handleTrial = async (clientId: string) => {
    Modal.confirm({
      title: '开通半年试用',
      content: `输入客户手机号（用于客户端登录验证）`,
      onOk: () => new Promise<void>((resolve) => {
        const phone = prompt('请输入手机号:')
        if (phone) {
          subscriptionApi.trial(clientId, phone).then(() => {
            message.success('已开通半年试用'); fetchSubs(); resolve()
          }).catch(() => { message.error('开通失败'); resolve() })
        } else { resolve() }
      }),
    })
  }

  const handleRenew = async (subId: string) => {
    Modal.confirm({
      title: '确认续费？',
      content: '将按当前会员等级续期',
      onOk: async () => {
        try {
          await subscriptionApi.renew(subId)
          message.success('续费成功')
          fetchSubs()
        } catch { message.error('续费失败') }
      },
    })
  }

  const handleSendMsg = (record: any) => {
    setMsgClient(record)
    msgForm.resetFields()
    setMsgModalOpen(true)
  }

  const handleSendMsgSubmit = async () => {
    const values = await msgForm.validateFields()
    setMsgSending(true)
    try {
      await interactionApi.sendToClient({
        client_id: msgClient.client_id,
        title: values.title,
        message: values.message,
        link: values.link || '/dashboard',
      })
      message.success('消息已发送至客户端')
      setMsgModalOpen(false)
    } catch { message.error('发送失败') }
    setMsgSending(false)
  }

  const columns = [
    { title: '客户', dataIndex: 'client_name', key: 'name' },
    { title: '绑定手机', dataIndex: 'phone', key: 'phone' },
    {
      title: '会员等级', dataIndex: 'tier', key: 'tier',
      render: (t: string, r: any) => {
        if (t === 'vip') return <Tag color="gold" icon={<CrownOutlined />}>{r.tier_label}</Tag>
        if (t === 'trial') return <Tag color="blue">{r.tier_label}</Tag>
        return <Tag color="default">未开通</Tag>
      },
    },
    {
      title: '状态', dataIndex: 'status', key: 'status',
      render: (s: string) => {
        if (s === 'active') return <Tag color="green">有效</Tag>
        if (s === 'expired') return <Tag color="red">已过期</Tag>
        if (s === 'cancelled') return <Tag color="default">已取消</Tag>
        return <Tag>--</Tag>
      },
    },
    {
      title: '到期日', dataIndex: 'end_date', key: 'end_date',
      render: (v: string, r: any) => (
        <Space>
          <Text>{v || '--'}</Text>
          {r.days_left > 0 && r.days_left <= 30 && <Tag color="orange">剩余 {r.days_left} 天</Tag>}
          {r.days_left === 0 && r.tier !== 'none' && <Tag color="red">已到期</Tag>}
        </Space>
      ),
    },
    {
      title: '操作', key: 'actions',
      render: (_: any, r: any) => {
        if (r.tier === 'none') {
          return <Button type="link" size="small" onClick={() => handleTrial(r.client_id)}>开通试用</Button>
        }
        return (
          <Space>
            {r.tier !== 'vip' && (
              <Tooltip title="服务端授权升级为 VIP 年费会员">
                <Button type="link" size="small" icon={<CrownOutlined />}
                  onClick={() => handleUpgrade(r.client_id, r.phone)}>升级VIP</Button>
              </Tooltip>
            )}
            {r.status !== 'active' && (
              <Button type="link" size="small" onClick={() => handleRenew(r.subscription_id)}>续费</Button>
            )}
            <Button type="link" size="small" onClick={() => handleSendMsg(r)}>发送消息</Button>
          </Space>
        )
      },
    },
  ]

  return (
    <div>
      <div style={{ marginBottom: 12, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Text strong style={{ fontSize: 14 }}>客户订阅管理 — 服务端授权</Text>
        <Button size="small" icon={<ReloadOutlined />} loading={loading} onClick={fetchSubs}>刷新</Button>
      </div>
      <Table dataSource={subs} columns={columns} rowKey="client_id" size="small" pagination={false} loading={loading} />

      <Modal
        title={`发送消息 — ${msgClient?.client_name || ''}`}
        open={msgModalOpen}
        onOk={handleSendMsgSubmit}
        onCancel={() => setMsgModalOpen(false)}
        confirmLoading={msgSending}
        okText="发送"
      >
        <Form form={msgForm} layout="vertical">
          <Form.Item label="消息标题" name="title" rules={[{ required: true, message: '请输入消息标题' }]}>
            <Input placeholder="如：申报进度通知、材料补充提醒" maxLength={100} />
          </Form.Item>
          <Form.Item label="消息内容" name="message" rules={[{ required: true, message: '请输入消息内容' }]}>
            <Input.TextArea rows={4} placeholder="输入要发送给客户的消息内容" maxLength={500} />
          </Form.Item>
          <Form.Item label="跳转链接（可选）" name="link">
            <Input placeholder="/dashboard 或 /documents" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}


function AutomationTab() {
  const { message } = App.useApp()
  const [status, setStatus] = useState<any>(null)
  const [folders, setFolders] = useState<any[]>([])
  const [collectors, setCollectors] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [folderModalOpen, setFolderModalOpen] = useState(false)
  const [emailModalOpen, setEmailModalOpen] = useState(false)
  const [folderForm] = Form.useForm()
  const [emailForm] = Form.useForm()

  const fetchAll = async () => {
    setLoading(true)
    try {
      const [statusRes, folderRes, collRes] = await Promise.all([
        automationApi.status(),
        automationApi.hotFolders(),
        automationApi.emailCollectors(),
      ])
      setStatus(statusRes)
      setFolders(folderRes.configs || folderRes.items || [])
      setCollectors(collRes.configs || collRes.items || [])
    } catch { /* ignore */ }
    setLoading(false)
  }

  useEffect(() => { fetchAll() }, [])

  const handleAddFolder = async () => {
    const values = await folderForm.validateFields()
    try {
      await automationApi.addHotFolder(values)
      message.success('热文件夹已添加')
      setFolderModalOpen(false)
      folderForm.resetFields()
      fetchAll()
    } catch (e: any) { message.error(e?.detail || '添加失败') }
  }

  const handleToggleFolder = async (id: string, enabled: boolean) => {
    try { await automationApi.toggleHotFolder(id, enabled); fetchAll() } catch { message.error('操作失败') }
  }

  const handleRemoveFolder = (id: string, label: string) => {
    Modal.confirm({
      title: '确认移除', content: `确定要移除监控「${label}」吗？`,
      onOk: async () => { try { await automationApi.removeHotFolder(id); message.success('已移除'); fetchAll() } catch { message.error('移除失败') } },
    })
  }

  const handleAddEmail = async () => {
    const values = await emailForm.validateFields()
    try {
      await automationApi.addEmailCollector(values)
      message.success('邮件采集器已添加')
      setEmailModalOpen(false)
      emailForm.resetFields()
      fetchAll()
    } catch (e: any) { message.error(e?.detail || '添加失败') }
  }

  const handleToggleEmail = async (id: string, enabled: boolean) => {
    try { await automationApi.toggleEmailCollector(id, enabled); fetchAll() } catch { message.error('操作失败') }
  }

  const handleRemoveEmail = (id: string, user: string) => {
    Modal.confirm({
      title: '确认移除', content: `确定要移除采集器「${user}」吗？`,
      onOk: async () => { try { await automationApi.removeEmailCollector(id); message.success('已移除'); fetchAll() } catch { message.error('移除失败') } },
    })
  }

  const handleTestEmail = async (id: string) => {
    try {
      const res: any = await automationApi.testEmailCollector(id)
      message.success(res.message || '测试完成')
    } catch (e: any) { message.error(e?.detail || '测试失败') }
  }

  const handleZipImport = async (file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('client_id', 'default')
    try {
      const res: any = await automationApi.zipImport(formData)
      message.success(res.message || '导入完成')
    } catch (e: any) { message.error(e?.detail || '导入失败') }
    return false
  }

  return (
    <div>
      {/* 状态概览 */}
      {status && (
        <div style={{ marginBottom: 16, display: 'flex', gap: 12 }}>
          <Card size="small" style={{ flex: 1, borderColor: status.hot_folders?.running ? '#52c41a' : '#e2e8f0' }}>
            <Text strong>热文件夹</Text>
            <div style={{ marginTop: 4 }}>
              <Tag color={status.hot_folders?.running ? 'green' : 'default'}>{status.hot_folders?.running ? '运行中' : '已停止'}</Tag>
              <Text type="secondary" style={{ fontSize: 12 }}>{status.hot_folders?.count || 0}/{status.hot_folders?.total || 0} 活跃</Text>
            </div>
          </Card>
          <Card size="small" style={{ flex: 1, borderColor: status.email_collectors?.running ? '#52c41a' : '#e2e8f0' }}>
            <Text strong>邮件采集</Text>
            <div style={{ marginTop: 4 }}>
              <Tag color={status.email_collectors?.running ? 'green' : 'default'}>{status.email_collectors?.running ? '运行中' : '已停止'}</Tag>
              <Text type="secondary" style={{ fontSize: 12 }}>{status.email_collectors?.count || 0}/{status.email_collectors?.total || 0} 活跃</Text>
            </div>
          </Card>
          <Card size="small" style={{ flex: 1 }}>
            <Text strong>Webhooks</Text>
            <div style={{ marginTop: 4 }}>
              <Text type="secondary" style={{ fontSize: 12 }}>{status.webhooks?.active || 0}/{status.webhooks?.total || 0} 活跃</Text>
            </div>
          </Card>
          <Card size="small" style={{ flex: 1 }}>
            <Text strong>ZIP导入</Text>
            <div style={{ marginTop: 4 }}><Tag color="green">就绪</Tag></div>
          </Card>
        </div>
      )}

      <Divider orientation="left" style={{ fontSize: 13 }}>热文件夹监控</Divider>
      <div style={{ marginBottom: 16, padding: 12, background: '#eff6ff', borderRadius: 6, border: '1px solid #bfdbfe', fontSize: 12, color: '#64748b' }}>
        将文件夹路径添加到监控列表，系统每 10 秒扫描一次。新文件自动入库 → OCR → 生成凭证 → 创建申报。支持：JPG/PNG/PDF/OFD/DOCX/XLSX。
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}>
        <Text strong style={{ fontSize: 13 }}>监控目录</Text>
        <Button size="small" icon={<PlusOutlined />} onClick={() => { folderForm.resetFields(); setFolderModalOpen(true) }}>添加目录</Button>
      </div>
      <Table
        dataSource={folders}
        columns={[
          { title: '名称', dataIndex: 'label', key: 'label', ellipsis: true },
          { title: '路径', dataIndex: 'path', key: 'path', ellipsis: true, render: (v: string) => <Text code style={{ fontSize: 11 }}>{v}</Text> },
          { title: '客户', dataIndex: 'client_id', key: 'client_id', width: 100 },
          { title: '来源', dataIndex: 'source', key: 'source', width: 90, render: (s: string) => <Tag>{s === 'scanner' ? '扫描仪' : '热文件夹'}</Tag> },
          {
            title: '状态', dataIndex: 'enabled', key: 'enabled', width: 80,
            render: (enabled: boolean, record: any) => (
              <Switch size="small" checked={enabled} onChange={(v) => handleToggleFolder(record.id, v)} />
            ),
          },
          {
            title: '操作', key: 'actions', width: 60,
            render: (_: any, r: any) => (
              <Button type="link" size="small" danger icon={<DeleteOutlined />} onClick={() => handleRemoveFolder(r.id, r.label)} />
            ),
          },
        ]}
        rowKey="id" size="small" pagination={false} loading={loading}
        locale={{ emptyText: '暂无监控目录，点击「添加目录」开始配置' }}
      />

      <Divider orientation="left" style={{ fontSize: 13, marginTop: 24 }}>邮件轮询采集</Divider>
      <div style={{ marginBottom: 16, padding: 12, background: '#f5f3ff', borderRadius: 6, border: '1px solid #ddd6fe', fontSize: 12, color: '#64748b' }}>
        配置 IMAP 邮箱，系统定期轮询邮件附件，自动下载发票/票据文件并入库加工。支持任何支持 IMAP 的邮箱。
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}>
        <Text strong style={{ fontSize: 13 }}>邮件采集器</Text>
        <Button size="small" icon={<PlusOutlined />} onClick={() => { emailForm.resetFields(); setEmailModalOpen(true) }}>添加采集器</Button>
      </div>
      <Table
        dataSource={collectors}
        columns={[
          { title: '邮箱', dataIndex: 'imap_user', key: 'user', ellipsis: true },
          { title: '主机', dataIndex: 'imap_host', key: 'host', width: 160, ellipsis: true },
          { title: '客户', dataIndex: 'client_id', key: 'client_id', width: 100 },
          { title: '文件夹', dataIndex: 'folder', key: 'folder', width: 80 },
          { title: '间隔', dataIndex: 'interval_minutes', key: 'interval', width: 70, render: (v: number) => `${v}分` },
          {
            title: '状态', dataIndex: 'enabled', key: 'enabled', width: 80,
            render: (enabled: boolean, record: any) => (
              <Switch size="small" checked={enabled} onChange={(v) => handleToggleEmail(record.id, v)} />
            ),
          },
          {
            title: '操作', key: 'actions', width: 120,
            render: (_: any, r: any) => (
              <Space size={0}>
                <Button type="link" size="small" onClick={() => handleTestEmail(r.id)}>测试</Button>
                <Button type="link" size="small" danger icon={<DeleteOutlined />} onClick={() => handleRemoveEmail(r.id, r.imap_user)} />
              </Space>
            ),
          },
        ]}
        rowKey="id" size="small" pagination={false} loading={loading}
        locale={{ emptyText: '暂无邮件采集器，点击「添加采集器」开始配置' }}
      />

      <Divider orientation="left" style={{ fontSize: 13, marginTop: 24 }}>ZIP 批量导入</Divider>
      <div style={{ marginBottom: 16, padding: 12, background: '#fefce8', borderRadius: 6, border: '1px solid #fde68a', fontSize: 12, color: '#64748b' }}>
        上传 ZIP 压缩包（最大 100MB），系统自动解压并逐张入库。支持 JPG/PNG/PDF/OFD。
      </div>
      <Upload accept=".zip" beforeUpload={handleZipImport} showUploadList={false}>
        <Button icon={<UploadOutlined />}>选择 ZIP 文件导入</Button>
      </Upload>

      <Modal title="添加热文件夹" open={folderModalOpen} onOk={handleAddFolder} onCancel={() => setFolderModalOpen(false)} okText="添加">
        <Form form={folderForm} layout="vertical" initialValues={{ source: 'hot_folder' }}>
          <Form.Item label="文件夹路径" name="path" rules={[{ required: true, message: '请输入文件夹路径' }]}>
            <Input placeholder="如 D:\扫描件\进项发票" />
          </Form.Item>
          <Form.Item label="关联客户" name="client_id" rules={[{ required: true, message: '请输入客户ID' }]}>
            <Input placeholder="客户 ID" />
          </Form.Item>
          <Form.Item label="名称" name="label"><Input placeholder="如：张会计发票文件夹" /></Form.Item>
          <Form.Item label="来源类型" name="source">
            <Select options={[{ label: '热文件夹', value: 'hot_folder' }, { label: '扫描仪', value: 'scanner' }]} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal title="添加邮件采集器" open={emailModalOpen} onOk={handleAddEmail} onCancel={() => setEmailModalOpen(false)} okText="添加" width={520}>
        <Form form={emailForm} layout="vertical" initialValues={{ folder: 'INBOX', interval_minutes: 5 }}>
          <Form.Item label="IMAP 服务器" name="imap_host" rules={[{ required: true }]}>
            <Input placeholder="如 imap.qq.com" />
          </Form.Item>
          <Form.Item label="邮箱账号" name="imap_user" rules={[{ required: true }]}>
            <Input placeholder="如 zhangsan@qq.com" />
          </Form.Item>
          <Form.Item label="邮箱密码/授权码" name="imap_pass" rules={[{ required: true }]}>
            <Input.Password placeholder="IMAP 授权码（非邮箱密码）" />
          </Form.Item>
          <Form.Item label="关联客户" name="client_id" rules={[{ required: true }]}>
            <Input placeholder="客户 ID" />
          </Form.Item>
          <Space size={12}>
            <Form.Item label="邮件文件夹" name="folder"><Input placeholder="INBOX" style={{ width: 120 }} /></Form.Item>
            <Form.Item label="轮询间隔(分)" name="interval_minutes"><InputNumber min={1} max={60} style={{ width: 100 }} /></Form.Item>
          </Space>
        </Form>
      </Modal>
    </div>
  )
}


function WebhookTab() {
  const { message } = App.useApp()
  const [webhooks, setWebhooks] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [addModalOpen, setAddModalOpen] = useState(false)
  const [addForm] = Form.useForm()

  const fetchWebhooks = async () => {
    setLoading(true)
    try {
      const res: any = await automationApi.webhooks()
      setWebhooks(res.items || [])
    } catch { message.error('获取 webhook 列表失败') }
    setLoading(false)
  }

  useEffect(() => { fetchWebhooks() }, [])

  const handleAdd = async () => {
    const values = await addForm.validateFields()
    try {
      const res: any = await automationApi.addWebhook(values)
      message.success(`${values.platform === 'wechat' ? '微信' : '钉钉'} webhook 已创建`)
      setAddModalOpen(false)
      addForm.resetFields()
      fetchWebhooks()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '创建失败')
    }
  }

  const handleToggle = async (id: string, enabled: boolean) => {
    try {
      await automationApi.toggleWebhook(id, enabled)
      message.success(enabled ? '已启用' : '已禁用')
      fetchWebhooks()
    } catch { message.error('操作失败') }
  }

  const handleDelete = (id: string, name: string) => {
    Modal.confirm({
      title: '确认删除',
      content: `确定要删除 webhook「${name}」吗？删除后对应的机器人将无法接收消息。`,
      onOk: async () => {
        try {
          await automationApi.removeWebhook(id)
          message.success('已删除')
          fetchWebhooks()
        } catch { message.error('删除失败') }
      },
    })
  }

  const handleCopyUrl = (url: string) => {
    const fullUrl = `${window.location.origin}/api${url}`
    navigator.clipboard.writeText(fullUrl).then(
      () => message.success('Webhook URL 已复制到剪贴板'),
      () => message.error('复制失败')
    )
  }

  const platformLabel = (p: string) => {
    if (p === 'wechat') return <Tag color="green" icon={<WechatOutlined />}>企业微信</Tag>
    if (p === 'dingtalk') return <Tag color="blue" icon={<DingdingOutlined />}>钉钉</Tag>
    return <Tag>{p}</Tag>
  }

  return (
    <div>
      <div style={{ marginBottom: 16, padding: 12, background: '#f0fdf4', borderRadius: 6, border: '1px solid #bbf7d0' }}>
        <Text style={{ fontSize: 13 }}>
          <Text strong>微信/钉钉集成说明：</Text><br />
          1. 创建 webhook 后，将回调 URL 配置到企业微信/钉钉机器人的消息接收地址<br />
          2. 用户向机器人发送发票、收据等文件时，系统自动采集入库并触发 OCR 识别<br />
          3. 每个客户可独立配置，支持随时启用/禁用
        </Text>
      </div>

      <div style={{ marginBottom: 12, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Text strong style={{ fontSize: 14 }}>Webhook 配置列表</Text>
        <Space>
          <Button size="small" icon={<ReloadOutlined />} loading={loading} onClick={fetchWebhooks}>刷新</Button>
          <Button type="primary" size="small" icon={<PlusOutlined />} onClick={() => { addForm.resetFields(); setAddModalOpen(true) }}>
            添加 Webhook
          </Button>
        </Space>
      </div>

      <Table
        dataSource={webhooks}
        columns={[
          { title: '名称', dataIndex: 'name', key: 'name' },
          {
            title: '平台', dataIndex: 'platform', key: 'platform', width: 120,
            render: (p: string) => platformLabel(p),
          },
          {
            title: '关联客户', dataIndex: 'client_id', key: 'client_id', width: 150,
            render: (v: string) => <Text code>{v}</Text>,
          },
          {
            title: '状态', dataIndex: 'enabled', key: 'enabled', width: 80,
            render: (enabled: boolean, record: any) => (
              <Button
                size="small"
                type={enabled ? 'primary' : 'default'}
                danger={!enabled}
                onClick={() => handleToggle(record.id, !enabled)}
              >
                {enabled ? '启用中' : '已禁用'}
              </Button>
            ),
          },
          {
            title: '累计采集', dataIndex: 'total_collected', key: 'collected', width: 80,
            render: (v: number) => <Tag color={v > 0 ? 'blue' : 'default'}>{v || 0} 张</Tag>,
          },
          {
            title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 160,
            render: (v: string) => v ? v.slice(0, 16).replace('T', ' ') : '-',
          },
          {
            title: '操作', key: 'actions', width: 200,
            render: (_: any, record: any) => (
              <Space size={0}>
                <Button type="link" size="small" icon={<CopyOutlined />}
                  onClick={() => handleCopyUrl(record.webhook_url)}>
                  复制URL
                </Button>
                <Button type="link" size="small" icon={<QrcodeOutlined />}
                  onClick={() => {
                    Modal.info({
                      title: `${platformLabel(record.platform)} Webhook 回调地址`,
                      content: (
                        <div style={{ textAlign: 'center', padding: 12 }}>
                          <div style={{ width: 160, height: 160, margin: '0 auto 12px', background: '#f1f5f9', borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', border: '2px dashed #cbd5e1' }}>
                            <QrcodeOutlined style={{ fontSize: 80, color: '#16a34a' }} />
                          </div>
                          <Text code copyable style={{ fontSize: 11, wordBreak: 'break-all' }}>
                            {window.location.origin}/api{record.webhook_url}
                          </Text>
                          <div style={{ marginTop: 8, fontSize: 12, color: '#64748b' }}>
                            将此地址配置到机器人消息推送 URL
                          </div>
                        </div>
                      ),
                      width: 460,
                    })
                  }}>
                  QR码
                </Button>
                <Button type="link" size="small" danger icon={<DeleteOutlined />}
                  onClick={() => handleDelete(record.id, record.name)}>
                  删除
                </Button>
              </Space>
            ),
          },
        ]}
        rowKey="id"
        size="small"
        pagination={false}
        loading={loading}
        locale={{ emptyText: '暂无 webhook 配置' }}
      />

      <Modal
        title="添加 Webhook 集成"
        open={addModalOpen}
        onOk={handleAdd}
        onCancel={() => setAddModalOpen(false)}
        okText="创建"
        width={500}
      >
        <Form form={addForm} layout="vertical" initialValues={{ platform: 'wechat' }}>
          <Form.Item label="平台" name="platform" rules={[{ required: true }]}>
            <Select options={[
              { label: '企业微信', value: 'wechat' },
              { label: '钉钉', value: 'dingtalk' },
            ]} />
          </Form.Item>
          <Form.Item label="关联客户" name="client_id" rules={[{ required: true, message: '请输入客户ID' }]}>
            <Input placeholder="客户 ID（如 u003）" />
          </Form.Item>
          <Form.Item label="名称" name="name">
            <Input placeholder="如：张会计微信机器人" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}


function AuditLogTab() {
  const { message } = App.useApp()
  const [logs, setLogs] = useState<any[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [filters, setFilters] = useState({ action: '', target_type: '', date_from: '', date_to: '' })

  const ACTION_LABELS: Record<string, string> = { created: '创建', updated: '修改', deleted: '删除', confirmed: '确认', reverted: '回滚', approved: '通过', rejected: '驳回', corrected: '更正', status_change: '状态变更' }
  const TARGET_LABELS: Record<string, string> = { voucher: '凭证', invoice: '发票', filing: '申报', document: '票据', client: '客户', employee: '员工', payroll: '工资', account: '科目', system_config: '系统配置' }

  const fetchLogs = async () => {
    setLoading(true)
    try {
      const params: any = { page, page_size: 20 }
      if (filters.action) params.action = filters.action
      if (filters.target_type) params.target_type = filters.target_type
      if (filters.date_from) params.date_from = filters.date_from
      if (filters.date_to) params.date_to = filters.date_to
      const res: any = await auditApi.logs(params)
      setLogs(res.items || [])
      setTotal(res.total || 0)
    } catch { message.error('加载操作日志失败') }
    setLoading(false)
  }

  useEffect(() => { fetchLogs() }, [page])

  const handleExport = async () => {
    try {
      const params: any = {}
      if (filters.action) params.action = filters.action
      if (filters.target_type) params.target_type = filters.target_type
      const res: any = await auditApi.exportLogs(params)
      const url = URL.createObjectURL(new Blob([res]))
      const a = document.createElement('a'); a.href = url; a.download = 'audit_logs.csv'; a.click()
      URL.revokeObjectURL(url)
      message.success('导出成功')
    } catch { message.error('导出失败') }
  }

  const columns = [
    { title: '时间', dataIndex: 'created_at', width: 170, render: (v: string) => v ? new Date(v).toLocaleString('zh-CN') : '-' },
    { title: '操作人', dataIndex: 'operator', width: 100 },
    { title: '操作', dataIndex: 'action', width: 80, render: (v: string) => <Tag>{ACTION_LABELS[v] || v}</Tag> },
    { title: '对象类型', dataIndex: 'target_type', width: 80, render: (v: string) => <Tag color="blue">{TARGET_LABELS[v] || v}</Tag> },
    { title: '对象ID', dataIndex: 'target_id', width: 140, ellipsis: true },
    { title: '详情', dataIndex: 'detail', ellipsis: true, render: (v: string) => <Text type="secondary" style={{ fontSize: 12 }}>{v || '-'}</Text> },
  ]

  return (
    <div>
      <Space style={{ marginBottom: 16 }} wrap>
        <Select placeholder="操作类型" allowClear style={{ width: 120 }} value={filters.action || undefined}
          onChange={(v) => { setFilters({ ...filters, action: v || '' }); setPage(1) }}
          options={Object.entries(ACTION_LABELS).map(([k, v]) => ({ label: v, value: k }))} />
        <Select placeholder="对象类型" allowClear style={{ width: 120 }} value={filters.target_type || undefined}
          onChange={(v) => { setFilters({ ...filters, target_type: v || '' }); setPage(1) }}
          options={Object.entries(TARGET_LABELS).map(([k, v]) => ({ label: v, value: k }))} />
        <Input type="date" placeholder="开始日期" style={{ width: 160 }}
          onChange={(e) => { setFilters({ ...filters, date_from: e.target.value }); setPage(1) }} />
        <Input type="date" placeholder="结束日期" style={{ width: 160 }}
          onChange={(e) => { setFilters({ ...filters, date_to: e.target.value }); setPage(1) }} />
        <Button onClick={() => { setPage(1); fetchLogs() }}>查询</Button>
        <Button icon={<DownloadOutlined />} onClick={handleExport}>导出CSV</Button>
      </Space>
      <Table dataSource={logs} columns={columns} rowKey="id" size="small" loading={loading}
        pagination={{ current: page, total, pageSize: 20, onChange: setPage, showTotal: (t: number) => `共 ${t} 条` }} />
    </div>
  )
}

function BackupTab() {
  const { message } = App.useApp()
  const [backing, setBacking] = useState(false)
  const [lastBackup, setLastBackup] = useState<any>(null)

  const handleBackup = async () => {
    setBacking(true)
    try {
      const res: any = await systemApi.backup()
      setLastBackup(res.data || res)
      message.success(res.message || '备份完成')
    } catch (e: any) {
      message.error(e?.detail || '备份失败')
    }
    setBacking(false)
  }

  const handleRestore = () => {
    Modal.confirm({
      title: '从备份恢复',
      content: '恢复将覆盖当前数据库中的所有数据，此操作不可撤销。\n请先确认已完成手动备份。',
      okText: '我已了解，继续恢复',
      okType: 'danger',
      onOk: async () => {
        const filename = prompt('请输入备份文件名（如 smart_tax_20260609_020000.db）：')
        if (!filename) return
        try {
          const res: any = await systemApi.restore(filename)
          message.success(res.message || '恢复成功')
        } catch (e: any) {
          message.error(e?.detail || '恢复失败')
        }
      },
    })
  }

  return (
    <div style={{ maxWidth: 500 }}>
      <div style={{ marginBottom: 16, padding: 12, background: '#fefce8', borderRadius: 6, border: '1px solid #fde68a' }}>
        <Text style={{ fontSize: 13 }}>
          <Text strong>自动备份：</Text>系统每日凌晨 2:00 自动备份数据库，保留最近 7 天。<br />
          <Text strong>手动备份：</Text>重大操作前建议手动触发一次备份。<br />
          备份文件存储在 <Text code>backups/</Text> 目录。
        </Text>
      </div>

      <Space>
        <Button type="primary" icon={<SaveOutlined />} loading={backing} onClick={handleBackup}>
          立即手动备份
        </Button>
        <Button danger onClick={handleRestore}>
          从备份恢复
        </Button>
      </Space>

      {lastBackup && (
        <Card size="small" style={{ marginTop: 16, borderColor: '#52c41a' }}>
          <Text strong style={{ color: '#16a34a' }}>备份成功</Text>
          <div style={{ marginTop: 8, fontSize: 12, color: '#64748b' }}>
            文件: <Text code>{lastBackup.file}</Text><br />
            大小: {lastBackup.size_mb} MB<br />
            时间: {lastBackup.timestamp}
          </div>
        </Card>
      )}
    </div>
  )
}


export default function Settings() {
  const { message } = App.useApp()
  const [companyForm] = Form.useForm()
  const [accForm] = Form.useForm()
  const [accounts, setAccounts] = useState<any[]>([])
  const [accModalOpen, setAccModalOpen] = useState(false)
  const allAccountsRef = useRef<any[]>([])

  const loadAccounts = async () => {
    try {
      const res: any = await accountApi.list({})
      const items = res.items || []
      allAccountsRef.current = items
      setAccounts(items)
    } catch { /* network unavailable */ }
  }

  const handleSearch = (keyword: string) => {
    if (!keyword.trim()) {
      setAccounts(allAccountsRef.current)
    } else {
      setAccounts(allAccountsRef.current.filter((a: any) =>
        a.code.includes(keyword) || a.name.includes(keyword)
      ))
    }
  }

  useEffect(() => {
    loadAccounts()
    settingsApi.get('company_info').then((res: any) => {
      if (res?.config_value && Object.keys(res.config_value).length > 0) companyForm.setFieldsValue(res.config_value)
    }).catch(() => {})
  }, [])

  const accountColumns = [
    { title: '科目编码', dataIndex: 'code', key: 'code', width: 120 },
    { title: '科目名称', dataIndex: 'name', key: 'name' },
    {
      title: '类别', dataIndex: 'category', key: 'category', width: 80,
      render: (c: string) => {
        const colors: Record<string, string> = { '资产': 'blue', '负债': 'orange', '权益': 'purple', '收入': 'green', '费用': 'red', '成本': 'cyan' }
        return <Tag color={colors[c] || 'default'}>{c}</Tag>
      },
    },
    {
      title: '余额方向', dataIndex: 'direction', key: 'direction', width: 80,
      render: (d: string) => <Tag color={d === 'debit' ? 'blue' : 'green'}>{d === 'debit' ? '借方' : '贷方'}</Tag>,
    },
  ]

  function UserManagementTab() {
    const { message } = App.useApp()
    const [users, setUsers] = useState<any[]>([])
    const [loading, setLoading] = useState(false)
    const [modalOpen, setModalOpen] = useState(false)
    const [editingUser, setEditingUser] = useState<any>(null)
    const [assignModalOpen, setAssignModalOpen] = useState(false)
    const [assignUserId, setAssignUserId] = useState<string>('')
    const [assignClientId, setAssignClientId] = useState<string>('')
    const [clients, setClients] = useState<any[]>([])
    const [userForm] = Form.useForm()

    const fetchUsers = async () => {
      setLoading(true)
      try {
        const res: any = await userApi.list()
        setUsers(res.items || [])
      } catch { message.error('获取用户列表失败') }
      setLoading(false)
    }

    useEffect(() => { fetchUsers() }, [])

    const openCreate = () => {
      setEditingUser(null)
      userForm.resetFields()
      setModalOpen(true)
    }

    const openEdit = (user: any) => {
      setEditingUser(user)
      userForm.setFieldsValue(user)
      setModalOpen(true)
    }

    const handleSave = async () => {
      const values = await userForm.validateFields()
      try {
        if (editingUser) {
          await userApi.update(editingUser.id, values)
          message.success('用户已更新')
        } else {
          await userApi.create(values)
          message.success('用户已创建')
        }
        setModalOpen(false)
        fetchUsers()
      } catch (e: any) { message.error(e?.detail || '操作失败') }
    }

    const openAssign = async (userId: string) => {
      setAssignUserId(userId)
      try {
        const res: any = await clientApi.list({ limit: 200 })
        setClients(res.items || [])
      } catch { setClients([]) }
      setAssignModalOpen(true)
    }

    const handleAssign = async () => {
      if (!assignClientId) { message.warning('请选择客户'); return }
      try {
        await userApi.assign(assignUserId, assignClientId)
        message.success('客户已分配给该用户')
        setAssignModalOpen(false)
        fetchUsers()
      } catch (e: any) { message.error(e?.detail || '分配失败') }
    }

    const handleUnassign = async (userId: string, clientId: string) => {
      try {
        await userApi.unassign(userId, clientId)
        message.success('已移除客户分配')
        fetchUsers()
      } catch (e: any) { message.error(e?.detail || '移除失败') }
    }

    const roleMap: Record<string, string> = {
      admin: '管理员', reviewer: '审核员', accountant: '会计', field_agent: '外勤', client: '客户', viewer: '观察员',
    }
    const roleColors: Record<string, string> = {
      admin: 'red', reviewer: 'orange', accountant: 'blue', field_agent: 'green', client: 'purple', viewer: 'default',
    }

    const columns = [
      { title: '姓名', dataIndex: 'display_name', key: 'name' },
      { title: '账号', dataIndex: 'username', key: 'username' },
      {
        title: '角色', dataIndex: 'role', key: 'role',
        render: (r: string) => <Tag color={roleColors[r] || 'default'}>{roleMap[r] || r}</Tag>,
      },
      {
        title: '所属客户', dataIndex: 'client_names', key: 'clients',
        render: (names: string[]) => names?.length ? names.map((n: string) => <Tag key={n}>{n}</Tag>) : <Text type="secondary">未分配</Text>,
      },
      {
        title: '操作', key: 'actions', width: 200,
        render: (_: any, record: any) => (
          <Space>
            <Button size="small" type="link" onClick={() => openEdit(record)}>编辑</Button>
            <Button size="small" type="link" onClick={() => openAssign(record.id)}>分配客户</Button>
            {record.client_ids?.map((cid: string) => (
              <Button key={cid} size="small" type="link" danger onClick={() => handleUnassign(record.id, cid)}>解除</Button>
            ))}
          </Space>
        ),
      },
    ]

    return (
      <div>
        <div style={{ marginBottom: 16, display: 'flex', gap: 16 }}>
          <Button icon={<PlusOutlined />} type="primary" onClick={openCreate}>新增用户</Button>
          <Button icon={<ReloadOutlined />} onClick={fetchUsers}>刷新</Button>
        </div>
        <Table dataSource={users} columns={columns} rowKey="id" loading={loading} size="small"
          locale={{ emptyText: '暂无用户' }} />

        <Modal title={editingUser ? '编辑用户' : '新增用户'} open={modalOpen}
          onCancel={() => setModalOpen(false)} onOk={handleSave}>
          <Form form={userForm} layout="vertical">
            <Form.Item label="用户名" name="username" rules={[{ required: true, message: '请输入用户名' }]}>
              <Input placeholder="登录用户名" maxLength={50} disabled={!!editingUser} />
            </Form.Item>
            {!editingUser && (
              <Form.Item label="密码" name="password" rules={[{ required: true, message: '请输入密码' }]}>
                <Input.Password placeholder="初始密码" maxLength={100} />
              </Form.Item>
            )}
            <Form.Item label="显示名称" name="display_name" rules={[{ required: true, message: '请输入显示名称' }]}>
              <Input placeholder="用户姓名" maxLength={50} />
            </Form.Item>
            <Form.Item label="角色" name="role" rules={[{ required: true, message: '请选择角色' }]}>
              <Select options={Object.entries(roleMap).map(([k, v]) => ({ label: v, value: k }))} />
            </Form.Item>
            {editingUser && (
              <Form.Item label="新密码（留空不修改）" name="password">
                <Input.Password placeholder="留空则不变更密码" maxLength={100} />
              </Form.Item>
            )}
          </Form>
        </Modal>

        <Modal title="分配客户" open={assignModalOpen}
          onCancel={() => setAssignModalOpen(false)} onOk={handleAssign} okText="确认分配">
          <Select
            value={assignClientId || undefined}
            onChange={setAssignClientId}
            style={{ width: '100%' }}
            placeholder="选择要分配的客户"
            options={clients.map((c: any) => ({ label: c.name, value: c.id }))}
          />
        </Modal>
      </div>
    )
  }

  const tabItems = [
    {
      key: 'accounts',
      label: '会计科目',
      children: (
        <div>
          <div style={{ marginBottom: 16, display: 'flex', gap: 16 }}>
            <Input.Search placeholder="搜索科目编码/名称" style={{ width: 300 }} onSearch={handleSearch} />
            <Button icon={<PlusOutlined />} onClick={() => { accForm.resetFields(); setAccModalOpen(true) }}>新增科目</Button>
          </div>
          <Table
            dataSource={accounts}
            columns={accountColumns}
            rowKey="code"
            size="small"
            pagination={false}
            onRow={() => ({ onClick: loadAccounts })}
            locale={{ emptyText: '点击搜索加载科目表' }}
          />
          <Button type="link" onClick={loadAccounts} style={{ marginTop: 8 }}>加载科目表</Button>

          <Modal title="新增会计科目" open={accModalOpen} onCancel={() => setAccModalOpen(false)}
            onOk={async () => {
              const vals = await accForm.validateFields()
              try {
                await accountApi.create(vals)
                message.success('科目创建成功')
                setAccModalOpen(false); loadAccounts()
              } catch { message.error('创建失败') }
            }}>
            <Form form={accForm} layout="vertical">
              <Form.Item label="科目编码" name="code" rules={[{ required: true }]}><Input /></Form.Item>
              <Form.Item label="科目名称" name="name" rules={[{ required: true }]}><Input /></Form.Item>
              <Form.Item label="科目类别" name="category"><Select options={[
                { label: '资产类', value: 'asset' }, { label: '负债类', value: 'liability' },
                { label: '权益类', value: 'equity' }, { label: '成本类', value: 'cost' },
                { label: '损益类', value: 'profit_loss' },
              ]} /></Form.Item>
              <Form.Item label="借贷方向" name="direction"><Select options={[
                { label: '借方', value: 'debit' }, { label: '贷方', value: 'credit' },
              ]} /></Form.Item>
              <Form.Item label="上级科目编码" name="parent_code"><Input /></Form.Item>
            </Form>
          </Modal>
        </div>
      ),
    },
    {
      key: 'tax_auto',
      label: '电子税务局',
      children: <TaxAutoConfig />,
    },
    {
      key: 'company',
      label: '企业信息',
      children: (
        <Form form={companyForm} layout="vertical" style={{ maxWidth: 500 }}
          initialValues={{ taxpayer_type: 'small' }}>
          <Form.Item label="企业名称" name="company_name">
            <Input placeholder="请输入企业名称" />
          </Form.Item>
          <Form.Item label="统一社会信用代码" name="tax_no">
            <Input placeholder="18位统一社会信用代码" />
          </Form.Item>
          <Form.Item label="纳税人性质" name="taxpayer_type">
            <Select options={[
              { label: '一般纳税人', value: 'general' },
              { label: '小规模纳税人', value: 'small' },
            ]} />
          </Form.Item>
          <Form.Item label="所属行业" name="industry">
            <Select options={[
              { label: '商务服务业', value: 'business_service' },
              { label: '信息技术', value: 'it' },
              { label: '批发零售', value: 'retail' },
              { label: '制造业', value: 'manufacturing' },
            ]} />
          </Form.Item>
          <Button type="primary" icon={<SaveOutlined />} onClick={async () => {
            try { await settingsApi.update('company_info', companyForm.getFieldsValue()); message.success('保存成功') } catch { message.error('保存失败') }
          }}>保存</Button>
        </Form>
      ),
    },
    {
      key: 'staff_usage',
      label: '人员使用状态',
      children: <StaffUsageTab />,
    },
    {
      key: 'user_mgmt',
      label: '用户管理',
      children: <UserManagementTab />,
    },
    {
      key: 'subscriptions',
      label: '客户订阅',
      children: <SubscriptionTab />,
    },
    {
      key: 'automation',
      label: '自动化采集',
      children: <AutomationTab />,
    },
    {
      key: 'webhook',
      label: '微信/钉钉集成',
      children: <WebhookTab />,
    },
    {
      key: 'audit_log',
      label: '操作日志',
      children: <AuditLogTab />,
    },
    {
      key: 'backup',
      label: '数据库备份',
      children: <BackupTab />,
    },
  ]

  return (
    <div>
      <h2 style={{ marginBottom: 24 }}>系统设置</h2>
      {tabItems.map(item => (
        <Card key={item.key} size="small" title={item.label} style={{ marginBottom: 16 }}>
          {item.children}
        </Card>
      ))}
    </div>
  )
}
