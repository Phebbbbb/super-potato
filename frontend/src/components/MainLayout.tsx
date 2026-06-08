import { useState, useEffect } from 'react'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { Layout, Menu, Button, Select, Tag, Space, Dropdown, Avatar, Badge } from 'antd'
import {
  DashboardOutlined,
  FileTextOutlined,
  BookOutlined,
  RobotOutlined,
  AuditOutlined,
  QrcodeOutlined,
  BarChartOutlined,
  SettingOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  TeamOutlined,
  LogoutOutlined,
  UserOutlined,
  DollarOutlined,
  BankOutlined,
  EnvironmentOutlined,
  CustomerServiceOutlined,
  SafetyOutlined,
  ReadOutlined,
  SwapOutlined,
  BellOutlined,
  FileProtectOutlined,
  NotificationOutlined,
  PrinterOutlined,
} from '@ant-design/icons'
import { useClient } from '@/contexts/ClientContext'

const { Header, Sider, Content, Footer } = Layout

const menuItems = [
  { key: '/dashboard', icon: <DashboardOutlined />, label: '工作台' },
  { type: 'divider' as const },
  {
    key: 'group-tax', icon: <AuditOutlined />, label: '涉税申报',
    children: [
      { key: '/tax-filings', icon: <FileTextOutlined />, label: '全税种申报' },
      { key: '/invoicing', icon: <FileTextOutlined />, label: '开票中心' },
    ],
  },
  {
    key: 'group-doc', icon: <FileTextOutlined />, label: '票据管理',
    children: [
      { key: '/documents', icon: <FileTextOutlined />, label: '票据采集录入' },
      { key: '/trace', icon: <QrcodeOutlined />, label: '票据核验追溯' },
    ],
  },
  {
    key: 'group-ledger', icon: <BookOutlined />, label: '财税台账',
    children: [
      { key: '/vouchers', icon: <BookOutlined />, label: '账务凭证' },
      { key: '/reports', icon: <BarChartOutlined />, label: '财务报表' },
      { key: '/payroll', icon: <DollarOutlined />, label: '薪酬台账' },
      { key: '/bank-reconciliation', icon: <BankOutlined />, label: '银企对账' },
      { key: '/print-center', icon: <PrinterOutlined />, label: '账簿打印' },
    ],
  },
  {
    key: 'group-risk', icon: <SafetyOutlined />, label: '风控与工具',
    children: [
      { key: '/tax-risk', icon: <SafetyOutlined />, label: '税务风险自查' },
      { key: '/audit', icon: <AuditOutlined />, label: '内审中心' },
      { key: '/ai-agent', icon: <CustomerServiceOutlined />, label: '政策法规查询' },

    ],
  },
  { type: 'divider' as const },
  { key: '/clients', icon: <TeamOutlined />, label: '客户管理' },
  { key: '/field-tasks', icon: <EnvironmentOutlined />, label: '外勤任务' },
  { key: '/settings', icon: <SettingOutlined />, label: '系统设置' },
  { key: '/guide', icon: <ReadOutlined />, label: '使用手册' },
]

export default function MainLayout() {
  const [collapsed, setCollapsed] = useState(false)
  const [openKeys, setOpenKeys] = useState<string[]>(['group-tax', 'group-doc', 'group-ledger', 'group-risk'])
  const navigate = useNavigate()
  const location = useLocation()
  const { currentClientId, clientList, switchClient } = useClient()

  useEffect(() => {
    const t = localStorage.getItem('token')
    if (!t && location.pathname !== '/login') {
      navigate('/login')
    }
  }, [location.pathname])

  const userStr = localStorage.getItem('user')
  const user = userStr ? JSON.parse(userStr) : null

  const handleLogout = () => {
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    localStorage.removeItem('client_ids')
    navigate('/login')
  }

  const currentClient = clientList.find(c => c.id === currentClientId)

  return (
    <Layout style={{ minHeight: '100vh' }}>
      {/* ===== 侧边栏 ===== */}
      <Sider
        trigger={null}
        collapsible
        collapsed={collapsed}
        width={230}
        style={{
          background: '#f8fafc',
          borderRight: '1px solid #e2e8f0',
          overflow: 'auto',
          height: '100vh',
          position: 'fixed',
          left: 0,
          top: 0,
          bottom: 0,
          zIndex: 10,
        }}
      >
        {/* Logo */}
        <div style={{
          height: 56,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 10,
          borderBottom: '1px solid #e2e8f0',
        }}>
          <img src="/vite.svg" alt="logo" style={{ width: 30, height: 30, minWidth: 30 }} />
          {!collapsed && (
            <span style={{ fontSize: 16, fontWeight: 700, color: '#1e3a5f', letterSpacing: 2, whiteSpace: 'nowrap' }}>
              账爻爻
            </span>
          )}
        </div>

        <Menu
          mode="inline"
          selectedKeys={[location.pathname]}
          openKeys={collapsed ? [] : openKeys}
          onOpenChange={setOpenKeys}
          items={menuItems}
          onClick={({ key }) => { if (key.startsWith('/')) navigate(key) }}
          style={{
            background: 'transparent',
            borderInlineEnd: 'none',
            padding: '6px 0',
          }}
        />
      </Sider>

      <Layout style={{ marginLeft: collapsed ? 80 : 230, transition: 'margin-left 0.2s' }}>
        {/* ===== 顶部导航 ===== */}
        <Header style={{
          padding: '0 20px',
          background: '#fff',
          display: 'flex',
          alignItems: 'center',
          gap: 16,
          height: 56,
          borderBottom: '1px solid #e2e8f0',
          boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
        }}>
          <Button
            type="text"
            icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            onClick={() => setCollapsed(!collapsed)}
            style={{ fontSize: 16 }}
          />

          {/* 品牌名 */}
          <span style={{
            fontSize: 14,
            fontWeight: 600,
            color: '#1e3a5f',
            letterSpacing: 1,
            whiteSpace: 'nowrap',
          }}>
            账爻爻
          </span>

          <div style={{ flex: 1 }} />

          {/* 快捷操作 */}
          <Space size={4}>
            <Button type="text" icon={<FileProtectOutlined />} onClick={() => navigate('/ai-agent')} style={{ fontSize: 13 }}>
              政策法规
            </Button>
            <Button type="text" icon={<NotificationOutlined />} onClick={() => navigate('/settings')} style={{ fontSize: 13 }}>
              操作日志
            </Button>
            <Badge count={2} size="small" offset={[-2, 4]}>
              <Button type="text" icon={<BellOutlined />} style={{ fontSize: 15 }} />
            </Badge>
          </Space>

          <div style={{ width: 1, height: 20, background: '#e2e8f0' }} />

          {/* 企业切换 */}
          <Space size={8}>
            {currentClient && (
              <Tag color="blue" style={{ borderRadius: 4, fontSize: 12 }}>{currentClient.name}</Tag>
            )}
            <Select
              size="small"
              value={currentClientId || undefined}
              onChange={switchClient}
              style={{ width: 160 }}
              placeholder="切换企业主体"
              suffixIcon={<SwapOutlined />}
              options={clientList.map(c => ({ label: c.name, value: c.id }))}
            />
          </Space>

          <div style={{ width: 1, height: 20, background: '#e2e8f0' }} />

          {/* 用户 */}
          {user && (
            <Dropdown
              menu={{
                items: [
                  { key: 'name', label: `实名用户：${user.display_name}`, disabled: true },
                  { key: 'role', label: `权限角色：${user.role === 'admin' ? '管理员' : user.role}`, disabled: true },
                  { type: 'divider' },
                  { key: 'audit', icon: <SafetyOutlined />, label: '实名操作全程留痕，财税数据依法留存五年', disabled: true },
                  { type: 'divider' },
                  { key: 'logout', icon: <LogoutOutlined />, label: '退出登录', onClick: handleLogout },
                ],
              }}
              placement="bottomRight"
            >
              <Space style={{ cursor: 'pointer', padding: '2px 8px', borderRadius: 6, transition: 'background 0.2s' }}
                onMouseEnter={e => (e.currentTarget.style.background = '#f1f5f9')}
                onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
              >
                <Avatar size={30} icon={<UserOutlined />} style={{ background: '#2563eb' }} />
                <span style={{ fontSize: 13, fontWeight: 500 }}>{user.display_name}</span>
                <Tag color={user.role === 'admin' ? 'blue' : 'default'} style={{ fontSize: 11, borderRadius: 4 }}>
                  {user.role === 'admin' ? '管理员' : user.role}
                </Tag>
              </Space>
            </Dropdown>
          )}
        </Header>

        {/* ===== 工作区 ===== */}
        <Content style={{
          padding: '12px 20px 28px',
          background: '#f1f5f9',
          minHeight: 'calc(100vh - 56px)',
        }}>
          <div className="content-card" style={{
            background: '#fff',
            borderRadius: 8,
            border: '1px solid #e2e8f0',
            padding: 16,
            minHeight: 'calc(100vh - 56px - 52px)',
          }}>
            <Outlet />
          </div>
        </Content>

        {/* ===== 底部合规信息（固定，不随页面滚动）===== */}
        <Footer style={{
          position: 'fixed',
          bottom: 0,
          left: collapsed ? 80 : 230,
          right: 0,
          background: '#f8fafc',
          borderTop: '1px solid #e2e8f0',
          padding: '4px 24px',
          display: 'flex',
          justifyContent: 'center',
          fontSize: 11,
          color: '#94a3b8',
          gap: 24,
          zIndex: 10,
          transition: 'left 0.2s',
        }}>
          <span>京ICP备2026XXXXXX号 | 京财税备2026XXXX号</span>
          <span>实名留痕 · 加密存储 · 依法留存</span>
          <span>税务热线：12366</span>
        </Footer>
      </Layout>
    </Layout>
  )
}
