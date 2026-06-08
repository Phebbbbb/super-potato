import { useState, useEffect, useRef } from 'react'
import { Card, Tabs, Table, Form, Input, Select, Button, Space, App, Tag, Typography, Modal } from 'antd'
import { PlusOutlined, SaveOutlined, HistoryOutlined, ReloadOutlined } from '@ant-design/icons'
import { accountApi, settingsApi, versionApi } from '@/services/api'
import dayjs from 'dayjs'

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

export default function Settings() {
  const { message } = App.useApp()
  const [companyForm] = Form.useForm()
  const [accForm] = Form.useForm()
  const [accounts, setAccounts] = useState<any[]>([])
  const [accModalOpen, setAccModalOpen] = useState(false)
  const allAccountsRef = useRef<any[]>([])

  // 操作日志
  const [auditLogs, setAuditLogs] = useState<any[]>([])
  const [auditLoading, setAuditLoading] = useState(false)

  const loadAccounts = async () => {
    try {
      const res: any = await accountApi.list({})
      const items = res.items || []
      allAccountsRef.current = items
      setAccounts(items)
    } catch { /* network unavailable */ }
  }

  const loadAuditLogs = async () => {
    setAuditLoading(true)
    try {
      const res: any = await versionApi.recent(100)
      setAuditLogs(res.data?.items || [])
    } catch { message.error('加载操作日志失败') }
    setAuditLoading(false)
  }

  useEffect(() => { loadAuditLogs() }, [])

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
      key: 'audit',
      label: <span><HistoryOutlined /> 操作日志</span>,
      children: (
        <div>
          <div style={{ marginBottom: 16 }}>
            <Button icon={<ReloadOutlined />} onClick={loadAuditLogs} loading={auditLoading}>刷新</Button>
            <Text type="secondary" style={{ marginLeft: 16 }}>所有增删改操作自动记录，支持版本回溯</Text>
          </div>
          <Table
            dataSource={auditLogs}
            rowKey="id"
            size="small"
            pagination={false}
            loading={auditLoading}
            locale={{ emptyText: '暂无操作记录' }}
            columns={[
              { title: '时间', dataIndex: 'created_at', width: 170, render: (v: string) => v ? dayjs(v).format('YYYY-MM-DD HH:mm:ss') : '-' },
              { title: '操作人', dataIndex: 'operator', width: 120 },
              {
                title: '操作', dataIndex: 'action', width: 100,
                render: (v: string) => {
                  const m: Record<string, { color: string; text: string }> = {
                    created: { color: 'green', text: '创建' },
                    updated: { color: 'blue', text: '修改' },
                    deleted: { color: 'red', text: '删除' },
                    confirmed: { color: 'cyan', text: '确认' },
                    reverted: { color: 'orange', text: '回滚' },
                  }
                  return <Tag color={m[v]?.color}>{m[v]?.text || v}</Tag>
                },
              },
              { title: '对象类型', dataIndex: 'target_type', width: 120, render: (v: string) => {
                const t: Record<string, string> = { voucher: '凭证', invoice: '发票', filing: '申报', document: '票据', client: '客户', employee: '员工' }
                return t[v] || v
              }},
              { title: '对象ID', dataIndex: 'target_id', width: 100, render: (v: string) => <Text code style={{ fontSize: 11 }}>{v?.slice(0, 8)}</Text> },
            ]}
          />
        </div>
      ),
    },
    {
      key: 'tax_auto',
      label: '税务自动化',
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
  ]

  return (
    <div>
      <h2 style={{ marginBottom: 24 }}>系统设置</h2>
      <Card style={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
        <Tabs items={tabItems} />
      </Card>
    </div>
  )
}
