import { useState, useEffect, useCallback } from 'react'
import { Card, Table, Button, Space, App, Typography, Tag, Modal, Descriptions, Popconfirm, Statistic, Row, Col, Tooltip } from 'antd'
import { CrownOutlined, GiftOutlined, RedoOutlined, ReloadOutlined, UserOutlined, HistoryOutlined } from '@ant-design/icons'
import { subscriptionApi, staffApi } from '@/services/api'
import dayjs from 'dayjs'

const { Text } = Typography

export default function Subscriptions() {
  const { message } = App.useApp()

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h2 style={{ margin: 0 }}>订阅管理</h2>
        <Text type="secondary">客户订阅套餐 · 人员使用状态 · 登录历史</Text>
      </div>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={12}><SubscriptionList /></Col>
        <Col span={12}><StaffUsage /></Col>
      </Row>
      <StaffLoginHistory />
    </div>
  )
}

function SubscriptionList() {
  const [items, setItems] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const { message } = App.useApp()

  const fetch = useCallback(async () => {
    setLoading(true)
    try { const res: any = await subscriptionApi.list(); setItems(res.subscriptions || []) } catch { /* */ }
    setLoading(false)
  }, [])

  useEffect(() => { fetch() }, [fetch])

  const handleTrial = async (clientId: string) => {
    try {
      const res: any = await subscriptionApi.trial(clientId, '')
      message.success('已开通半年试用')
      fetch()
    } catch { message.error('操作失败') }
  }

  const handleUpgrade = async (clientId: string) => {
    try {
      const res: any = await subscriptionApi.upgrade(clientId, '')
      message.success('已升级为 VIP')
      fetch()
    } catch { message.error('操作失败') }
  }

  const handleRenew = async (subId: string) => {
    try {
      const res: any = await subscriptionApi.renew(subId)
      message.success('续费成功')
      fetch()
    } catch { message.error('操作失败') }
  }

  const tierColor: Record<string, string> = { vip: 'gold', trial: 'blue', basic: 'default', none: 'default' }
  const tierLabel: Record<string, string> = { vip: 'VIP年费', trial: '试用中', basic: '基础版', none: '未开通' }

  return (
    <Card title="客户订阅" extra={<Button icon={<ReloadOutlined />} size="small" onClick={fetch}>刷新</Button>}>
      <Table dataSource={items} rowKey="client_id" loading={loading} size="small" pagination={false}
        locale={{ emptyText: '暂无订阅数据' }}
        columns={[
          { title: '客户', dataIndex: 'client_name', width: 120, ellipsis: true },
          { title: '套餐', dataIndex: 'tier', width: 90,
            render: (v: string) => <Tag color={tierColor[v] || 'default'}>{tierLabel[v] || v}</Tag> },
          { title: '到期日', dataIndex: 'end_date', width: 100,
            render: (v: string) => v ? dayjs(v).format('YYYY-MM-DD') : '-' },
          { title: '操作', width: 200,
            render: (_: any, r: any) => (
              <Space size={0}>
                {r.tier === 'none' && (
                  <Tooltip title="开通6个月试用"><Button type="link" size="small" icon={<GiftOutlined />} onClick={() => handleTrial(r.client_id)}>试用</Button></Tooltip>
                )}
                {(r.tier === 'trial' || r.tier === 'none' || r.tier === 'basic') && (
                  <Tooltip title="升级VIP年费"><Button type="link" size="small" icon={<CrownOutlined />} onClick={() => handleUpgrade(r.client_id)}>升级</Button></Tooltip>
                )}
                {r.subscription_id && r.tier !== 'none' && (
                  <Tooltip title="续费"><Button type="link" size="small" icon={<RedoOutlined />} onClick={() => handleRenew(r.subscription_id)}>续费</Button></Tooltip>
                )}
              </Space>
            )},
        ]} />
    </Card>
  )
}

function StaffUsage() {
  const [staff, setStaff] = useState<any[]>([])
  const [loading, setLoading] = useState(false)

  const fetch = useCallback(async () => {
    setLoading(true)
    try { const res: any = await staffApi.usage(); setStaff(res.staff || []) } catch { /* */ }
    setLoading(false)
  }, [])

  useEffect(() => { fetch() }, [fetch])

  return (
    <Card title="人员使用状态" extra={<Button icon={<ReloadOutlined />} size="small" onClick={fetch}>刷新</Button>}>
      <Table dataSource={staff} rowKey="user_id" loading={loading} size="small" pagination={false}
        locale={{ emptyText: '暂无数据' }}
        columns={[
          { title: '姓名', dataIndex: 'display_name', width: 80 },
          { title: '角色', dataIndex: 'role', width: 80,
            render: (v: string) => v === 'admin' ? <Tag color="blue">管理员</Tag> : v },
          { title: '最后登录', dataIndex: 'last_login', width: 130,
            render: (v: string) => v ? dayjs(v).format('MM-DD HH:mm') : '-' },
          { title: '今日操作', dataIndex: 'actions_today', width: 80 },
          { title: '活跃客户', dataIndex: 'active_clients', width: 80 },
        ]} />
    </Card>
  )
}

function StaffLoginHistory() {
  const [history, setHistory] = useState<any[]>([])
  const [loading, setLoading] = useState(false)

  const fetch = async (userId?: string) => {
    setLoading(true)
    try { const res: any = await staffApi.loginHistory(userId); setHistory(res.history || []) } catch { /* */ }
    setLoading(false)
  }

  useEffect(() => { fetch() }, [])

  return (
    <Card title="登录历史" extra={<Button icon={<ReloadOutlined />} size="small" onClick={() => fetch()}>刷新</Button>}>
      <Table dataSource={history} rowKey={(r: any) => r.id || r.logged_at} loading={loading} size="small"
        pagination={{ pageSize: 20, showSizeChanger: false }}
        locale={{ emptyText: '暂无记录' }}
        columns={[
          { title: '用户', dataIndex: 'display_name', width: 100 },
          { title: 'IP', dataIndex: 'ip', width: 140 },
          { title: '登录方式', dataIndex: 'login_type', width: 90, render: (v: string) => v === 'password' ? '密码' : v || '-' },
          { title: '时间', dataIndex: 'logged_at', width: 160,
            render: (v: string) => v ? dayjs(v).format('YYYY-MM-DD HH:mm:ss') : '-' },
        ]} />
    </Card>
  )
}
