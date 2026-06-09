import { useState } from 'react'
import { Card, Form, Input, Button, Typography, message } from 'antd'
import { UserOutlined, LockOutlined, SafetyOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'

const { Title, Text } = Typography

export default function Login() {
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  const handleLogin = async (values: any) => {
    setLoading(true)
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(values),
      })
      const data = await res.json()
      if (!res.ok) { message.error(data.detail || '登录失败'); setLoading(false); return }
      localStorage.setItem('token', data.token)
      localStorage.setItem('user', JSON.stringify(data.user))
      localStorage.setItem('client_ids', JSON.stringify(data.client_ids))
      if (data.client_ids && data.client_ids.length > 0) {
        localStorage.setItem('current_client_id', data.client_ids[0])
      }
      message.success(`欢迎回来，${data.user.display_name}`)
      navigate('/dashboard', { replace: true })
    } catch (e: any) {
      message.error(e?.message || '登录请求失败，请检查网络连接')
      setLoading(false)
    }
  }

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      flexDirection: 'column',
      background: '#f1f5f9',
    }}>
      <div style={{
        flex: 1,
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        padding: 24,
      }}>
        <div style={{ width: 400 }}>
          {/* Logo + 标题 */}
          <div style={{ textAlign: 'center', marginBottom: 28 }}>
            <img
              src="/vite.svg"
              alt="账爻爻"
              style={{ width: 52, height: 52, margin: '0 auto 12px', display: 'block' }}
            />
            <Title level={3} style={{ margin: '0 0 4px', color: '#1e3a5f', fontWeight: 700, letterSpacing: 3 }}>
              账爻爻
            </Title>
            <Text style={{ color: '#94a3b8', fontSize: 13 }}>
              智能财税管理平台
            </Text>
          </div>

          {/* 登录卡片 */}
          <Card
            style={{
              borderRadius: 8,
              border: '1px solid #e2e8f0',
              boxShadow: '0 4px 16px rgba(0,0,0,0.06)',
            }}
            styles={{ body: { padding: '32px 32px 24px' } }}
          >
            {/* 合规提示 */}
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              marginBottom: 20,
              padding: '8px 12px',
              background: '#f8fafc',
              borderRadius: 6,
              fontSize: 12,
              color: '#64748b',
            }}>
              <SafetyOutlined style={{ color: '#2563eb' }} />
              实名操作全程留痕，财税数据依法留存五年
            </div>

            <Form onFinish={handleLogin} size="large">
              <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }]}>
                <Input prefix={<UserOutlined style={{ color: '#94a3b8' }} />} placeholder="用户名" />
              </Form.Item>
              <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}>
                <Input.Password prefix={<LockOutlined style={{ color: '#94a3b8' }} />} placeholder="密码" />
              </Form.Item>
              <Form.Item style={{ marginBottom: 16 }}>
                <Button type="primary" htmlType="submit" loading={loading} block style={{ height: 42, fontSize: 15 }}>
                  登 录
                </Button>
              </Form.Item>
            </Form>

            <div style={{ textAlign: 'center', paddingTop: 12, borderTop: '1px dashed #e2e8f0' }}>
              <Text type="secondary" style={{ fontSize: 11 }}>
                请联系系统管理员获取账号
              </Text>
            </div>
          </Card>

          <div style={{ textAlign: 'center', marginTop: 20 }}>
            <Text style={{ color: '#cbd5e1', fontSize: 11 }}>
              版本 V2.1 &nbsp;|&nbsp; 智能财税 · 全自动税务机器人
            </Text>
          </div>
        </div>
      </div>

      {/* 底部 */}
      <div style={{
        background: '#f8fafc',
        borderTop: '1px solid #e2e8f0',
        padding: '10px 24px',
        textAlign: 'center',
      }}>
        <Text style={{ color: '#94a3b8', fontSize: 11 }}>
          税务咨询热线：12366 &nbsp;|&nbsp; 依据《税收征收管理法》，涉税数据加密存储，留存不少于5年
        </Text>
      </div>
    </div>
  )
}
