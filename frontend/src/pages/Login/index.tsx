import { useState, useEffect } from 'react'
import { Card, Form, Input, Button, Typography, Tabs, message, Checkbox, Modal, Space } from 'antd'
import { UserOutlined, LockOutlined, SafetyOutlined, PhoneOutlined, MessageOutlined, IdcardOutlined, KeyOutlined, UserAddOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'

const { Title, Text } = Typography

export default function Login() {
  const [loading, setLoading] = useState(false)
  const [activeTab, setActiveTab] = useState('service')
  const navigate = useNavigate()
  const [serviceForm] = Form.useForm()
  const [forgotForm] = Form.useForm()
  const [registerForm] = Form.useForm()

  // 记住密码：从 localStorage 恢复
  useEffect(() => {
    const saved = localStorage.getItem('remembered_username')
    if (saved) {
      serviceForm.setFieldsValue({ username: saved, remember: true })
    }
  }, [])

  // ===== 服务端登录 =====
  const handleServiceLogin = async (values: any) => {
    setLoading(true)
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: values.username, password: values.password, remember: values.remember || false }),
      })
      const data = await res.json()
      if (!res.ok) { message.error(data.detail || '登录失败'); setLoading(false); return }

      // 记住密码
      if (values.remember) {
        localStorage.setItem('remembered_username', values.username)
      } else {
        localStorage.removeItem('remembered_username')
      }

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

  // ===== 忘记密码 =====
  const [forgotOpen, setForgotOpen] = useState(false)
  const [forgotStep, setForgotStep] = useState<'phone' | 'reset'>('phone')
  const [forgotPhone, setForgotPhone] = useState('')
  const [forgotCodeSending, setForgotCodeSending] = useState(false)
  const [forgotCountdown, setForgotCountdown] = useState(0)
  const [forgotLoading, setForgotLoading] = useState(false)

  useEffect(() => {
    if (forgotCountdown > 0) {
      const timer = setTimeout(() => setForgotCountdown(c => c - 1), 1000)
      return () => clearTimeout(timer)
    }
  }, [forgotCountdown])

  const handleForgotSendCode = async () => {
    const phone = forgotForm.getFieldValue('phone')
    if (!phone || phone.length !== 11) { message.warning('请输入正确的11位手机号'); return }
    setForgotCodeSending(true)
    try {
      const res = await fetch('/api/auth/send-code', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone }),
      })
      const data = await res.json()
      if (!res.ok) { message.error(data.detail || '发送失败'); setForgotCodeSending(false); return }
      message.success('验证码已发送')
      setForgotPhone(phone)
      setForgotStep('reset')
      setForgotCountdown(60)
    } catch { message.error('发送失败') }
    setForgotCodeSending(false)
  }

  const handleForgotReset = async () => {
    const values = await forgotForm.validateFields()
    setForgotLoading(true)
    try {
      const res = await fetch('/api/auth/forgot-password', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone: forgotPhone, code: values.code, new_password: values.new_password }),
      })
      const data = await res.json()
      if (!res.ok) { message.error(data.detail || '重置失败'); setForgotLoading(false); return }
      message.success('密码重置成功，请使用新密码登录')
      setForgotOpen(false)
      setForgotStep('phone')
      forgotForm.resetFields()
    } catch { message.error('请求失败') }
    setForgotLoading(false)
  }

  // ===== 注册 =====
  const [registerOpen, setRegisterOpen] = useState(false)
  const [regCodeSending, setRegCodeSending] = useState(false)
  const [regCountdown, setRegCountdown] = useState(0)
  const [regLoading, setRegLoading] = useState(false)

  useEffect(() => {
    if (regCountdown > 0) {
      const timer = setTimeout(() => setRegCountdown(c => c - 1), 1000)
      return () => clearTimeout(timer)
    }
  }, [regCountdown])

  const handleRegSendCode = async () => {
    const phone = registerForm.getFieldValue('phone')
    if (!phone || phone.length !== 11) { message.warning('请输入正确的11位手机号'); return }
    setRegCodeSending(true)
    try {
      const res = await fetch('/api/auth/send-code', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone }),
      })
      if (!res.ok) { const d = await res.json(); message.error(d.detail || '发送失败'); setRegCodeSending(false); return }
      message.success('验证码已发送')
      setRegCountdown(60)
    } catch { message.error('发送失败') }
    setRegCodeSending(false)
  }

  const handleRegister = async () => {
    const values = await registerForm.validateFields()
    setRegLoading(true)
    try {
      const res = await fetch('/api/auth/register', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(values),
      })
      const data = await res.json()
      if (!res.ok) { message.error(data.detail || '注册失败'); setRegLoading(false); return }
      message.success('注册成功，已自动登录')
      localStorage.setItem('token', data.token)
      localStorage.setItem('user', JSON.stringify(data.user))
      localStorage.setItem('client_ids', JSON.stringify(data.client_ids || []))
      setRegisterOpen(false)
      registerForm.resetFields()
      navigate('/dashboard', { replace: true })
    } catch { message.error('请求失败') }
    setRegLoading(false)
  }

  // ===== 客户端手机验证码登录 =====
  const [codeSending, setCodeSending] = useState(false)
  const [countdown, setCountdown] = useState(0)

  useEffect(() => {
    if (countdown > 0) {
      const timer = setTimeout(() => setCountdown(c => c - 1), 1000)
      return () => clearTimeout(timer)
    }
  }, [countdown])

  const handleSendCode = async (phone: string) => {
    if (!phone || phone.length !== 11) { message.warning('请输入正确的11位手机号'); return }
    setCodeSending(true)
    try {
      const res = await fetch('/api/auth/send-code', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone }),
      })
      const data = await res.json()
      if (!res.ok) { message.error(data.detail || '发送失败'); setCodeSending(false); return }
      message.success('验证码已发送（开发模式：123456）')
      setCountdown(60)
    } catch { message.error('发送失败，请重试') }
    setCodeSending(false)
  }

  const handleClientLogin = async (values: any) => {
    setLoading(true)
    try {
      const res = await fetch('/api/auth/client-login', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
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
      if (data.subscription) {
        localStorage.setItem('subscription', JSON.stringify(data.subscription))
      }
      const subInfo = data.subscription
        ? ` | ${data.subscription.tier_label} (剩余${data.subscription.days_left}天)`
        : ''
      message.success(`登录成功${subInfo}`)
      navigate('/dashboard', { replace: true })
    } catch (e: any) {
      message.error(e?.message || '登录请求失败，请检查网络连接')
      setLoading(false)
    }
  }

  // ===== Tab 配置 =====
  const tabItems = [
    {
      key: 'service',
      label: '服务端登录',
      children: (
        <Form form={serviceForm} onFinish={handleServiceLogin} size="large">
          <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }]}>
            <Input prefix={<UserOutlined style={{ color: '#94a3b8' }} />} placeholder="用户名" />
          </Form.Item>
          <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}>
            <Input.Password prefix={<LockOutlined style={{ color: '#94a3b8' }} />} placeholder="密码" />
          </Form.Item>
          <Form.Item style={{ marginBottom: 8 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Form.Item name="remember" valuePropName="checked" noStyle>
                <Checkbox style={{ fontSize: 13 }}>记住密码</Checkbox>
              </Form.Item>
              <Button type="link" size="small" onClick={() => { setForgotOpen(true); forgotForm.resetFields(); setForgotStep('phone') }}
                style={{ padding: 0, fontSize: 12 }}>
                忘记密码？
              </Button>
            </div>
          </Form.Item>
          <Form.Item style={{ marginBottom: 16 }}>
            <Button type="primary" htmlType="submit" loading={loading} block style={{ height: 42, fontSize: 15 }}>
              登 录
            </Button>
          </Form.Item>
          <div style={{ textAlign: 'center', paddingTop: 12, borderTop: '1px dashed #e2e8f0' }}>
            <Space split={<span style={{ color: '#d1d5db' }}>|</span>}>
              <Text type="secondary" style={{ fontSize: 11 }}>服务端内部人员专用</Text>
              <Button type="link" size="small" onClick={() => { setRegisterOpen(true); registerForm.resetFields() }}
                style={{ padding: 0, fontSize: 11 }}>
                <UserAddOutlined /> 注册账号
              </Button>
            </Space>
          </div>
        </Form>
      ),
    },
    {
      key: 'client',
      label: '客户端登录',
      children: (
        <Form onFinish={handleClientLogin} size="large">
          <Form.Item name="tax_no" rules={[
            { required: true, message: '请输入统一社会信用代码' },
            { pattern: /^[0-9A-HJ-NPQRTUWXY]{2}\d{6}[0-9A-HJ-NPQRTUWXY]{10}$/, message: '统一社会信用代码格式不正确（18位）' },
          ]}>
            <Input prefix={<IdcardOutlined style={{ color: '#94a3b8' }} />} placeholder="统一社会信用代码（18位）" maxLength={18} style={{ fontFamily: 'monospace', letterSpacing: 1 }} />
          </Form.Item>
          <Form.Item name="phone" rules={[
            { required: true, message: '请输入11位手机号' },
            { pattern: /^1[3-9]\d{9}$/, message: '手机号格式不正确' },
          ]}>
            <Input prefix={<PhoneOutlined style={{ color: '#94a3b8' }} />} placeholder="手机号" maxLength={11} />
          </Form.Item>
          <Form.Item style={{ marginBottom: 16 }}>
            <div style={{ display: 'flex', gap: 12 }}>
              <Form.Item name="code" noStyle rules={[{ required: true, message: '请输入验证码' }]}>
                <Input prefix={<MessageOutlined style={{ color: '#94a3b8' }} />} placeholder="验证码" maxLength={6} style={{ flex: 1 }} />
              </Form.Item>
              <Button disabled={countdown > 0} loading={codeSending}
                onClick={() => {
                  const phone = (document.querySelector('input[placeholder="手机号"]') as HTMLInputElement)?.value
                  handleSendCode(phone)
                }}
                style={{ minWidth: 120, height: 42 }}>
                {countdown > 0 ? `${countdown}s 后重发` : '获取验证码'}
              </Button>
            </div>
          </Form.Item>
          <Form.Item style={{ marginBottom: 16 }}>
            <Button type="primary" htmlType="submit" loading={loading} block style={{ height: 42, fontSize: 15 }}>
              验 证 登 录
            </Button>
          </Form.Item>
          <div style={{ textAlign: 'center', paddingTop: 12, borderTop: '1px dashed #e2e8f0' }}>
            <Text type="secondary" style={{ fontSize: 11 }}>
              企业客户手机验证码登录 · 首次登录自动开通半年试用
            </Text>
          </div>
        </Form>
      ),
    },
  ]

  return (
    <div style={{
      minHeight: '100vh', display: 'flex', flexDirection: 'column',
      background: 'linear-gradient(135deg, #0f172a 0%, #1e293b 30%, #0c4a6e 60%, #172554 100%)',
      position: 'relative', overflow: 'hidden',
    }}>
      <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none',
        background: 'radial-gradient(ellipse at 20% 50%, rgba(37,99,235,0.15) 0%, transparent 50%), radial-gradient(ellipse at 80% 20%, rgba(124,58,237,0.12) 0%, transparent 50%), radial-gradient(ellipse at 50% 80%, rgba(2,132,199,0.10) 0%, transparent 50%)',
      }} />
      <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none',
        backgroundImage: 'linear-gradient(rgba(255,255,255,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px)',
        backgroundSize: '60px 60px',
      }} />

      <div style={{ flex: 1, display: 'flex', justifyContent: 'center', alignItems: 'center', padding: 24 }}>
        <div style={{ width: 420 }}>
          <div style={{ textAlign: 'center', marginBottom: 28 }}>
            <img src="/logo.svg" alt="爻一爻" style={{ width: 56, height: 56, margin: '0 auto 14px', display: 'block', filter: 'drop-shadow(0 2px 8px rgba(37,99,235,0.3))' }} />
            <Title level={2} style={{ margin: '0 0 4px', color: '#f1f5f9', fontWeight: 700, letterSpacing: 4, fontFamily: "'ZCOOL KuaiLe', 'Ma Shan Zheng', cursive", fontSize: 36 }}>
              爻一爻
            </Title>
            <Text style={{ color: '#94a3b8', fontSize: 13 }}>智能财税管理平台</Text>
          </div>

          <Card style={{ borderRadius: 8, border: '1px solid #e2e8f0', boxShadow: '0 4px 16px rgba(0,0,0,0.06)' }}
            styles={{ body: { padding: '28px 28px 20px' } }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 20, padding: '8px 12px', background: '#f8fafc', borderRadius: 6, fontSize: 12, color: '#64748b' }}>
              <SafetyOutlined style={{ color: '#2563eb' }} />
              实名操作全程留痕，财税数据依法留存五年
            </div>
            <Tabs activeKey={activeTab} onChange={setActiveTab} centered items={tabItems} style={{ marginTop: -8 }} />
          </Card>

          <div style={{ textAlign: 'center', marginTop: 20 }}>
            <Text style={{ color: '#cbd5e1', fontSize: 11 }}>版本 V2.3 &nbsp;|&nbsp; 智能财税 · 全自动税务机器人</Text>
          </div>
        </div>
      </div>

      <div style={{ background: '#f8fafc', borderTop: '1px solid #e2e8f0', padding: '10px 24px', textAlign: 'center' }}>
        <Text style={{ color: '#94a3b8', fontSize: 11 }}>
          税务咨询热线：12366 &nbsp;|&nbsp; 依据《税收征收管理法》，涉税数据加密存储，留存不少于5年
        </Text>
      </div>

      {/* 忘记密码弹窗 */}
      <Modal
        title={<Space><KeyOutlined style={{ color: '#2563eb' }} />忘记密码</Space>}
        open={forgotOpen}
        onCancel={() => { setForgotOpen(false); setForgotStep('phone'); forgotForm.resetFields() }}
        footer={null}
        width={380}
      >
        <Form form={forgotForm} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="phone" label="绑定手机号" rules={[
            { required: true, message: '请输入手机号' },
            { pattern: /^1[3-9]\d{9}$/, message: '手机号格式不正确' },
          ]}>
            <Input prefix={<PhoneOutlined />} placeholder="11位手机号" maxLength={11}
              disabled={forgotStep === 'reset'} />
          </Form.Item>
          {forgotStep === 'phone' ? (
            <Button type="primary" block loading={forgotCodeSending} onClick={handleForgotSendCode}
              style={{ height: 40 }}>
              获取验证码
            </Button>
          ) : (
            <>
              <Form.Item name="code" label="验证码" rules={[{ required: true, message: '请输入验证码' }]}>
                <Input prefix={<MessageOutlined />} placeholder="6位验证码" maxLength={6} />
              </Form.Item>
              <Form.Item name="new_password" label="新密码" rules={[
                { required: true, message: '请输入新密码' },
                { min: 6, message: '密码至少6位' },
              ]}>
                <Input.Password prefix={<LockOutlined />} placeholder="新密码（至少6位）" />
              </Form.Item>
              <Button type="primary" block loading={forgotLoading} onClick={handleForgotReset} style={{ height: 40 }}>
                重置密码
              </Button>
              <Button type="link" block size="small" onClick={() => { setForgotStep('phone'); forgotForm.resetFields() }}
                style={{ marginTop: 8 }}>
                返回上一步
              </Button>
            </>
          )}
        </Form>
      </Modal>

      {/* 注册弹窗 */}
      <Modal
        title={<Space><UserAddOutlined style={{ color: '#2563eb' }} />注册服务端账号</Space>}
        open={registerOpen}
        onCancel={() => { setRegisterOpen(false); registerForm.resetFields() }}
        footer={null}
        width={400}
      >
        <div style={{ marginBottom: 12, padding: '8px 12px', background: '#eff6ff', borderRadius: 6, fontSize: 12, color: '#1e40af', border: '1px solid #bfdbfe' }}>
          新注册账号默认为<strong>观察员</strong>权限，需管理员提升角色
        </div>
        <Form form={registerForm} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="username" label="用户名" rules={[
            { required: true, message: '请输入用户名' },
            { min: 2, max: 50, message: '2-50个字符' },
          ]}>
            <Input prefix={<UserOutlined />} placeholder="登录用户名" />
          </Form.Item>
          <Form.Item name="display_name" label="显示名称" rules={[{ required: true, message: '请输入显示名称' }]}>
            <Input prefix={<UserOutlined />} placeholder="如：张会计" />
          </Form.Item>
          <Form.Item name="phone" label="手机号" rules={[
            { required: true, message: '请输入手机号' },
            { pattern: /^1[3-9]\d{9}$/, message: '手机号格式不正确' },
          ]}>
            <Input prefix={<PhoneOutlined />} placeholder="11位手机号" maxLength={11} />
          </Form.Item>
          <Form.Item style={{ marginBottom: 8 }}>
            <div style={{ display: 'flex', gap: 12 }}>
              <Form.Item name="code" noStyle rules={[{ required: true, message: '请输入验证码' }]}>
                <Input prefix={<MessageOutlined />} placeholder="验证码" maxLength={6} style={{ flex: 1 }} />
              </Form.Item>
              <Button disabled={regCountdown > 0} loading={regCodeSending} onClick={handleRegSendCode}
                style={{ minWidth: 110 }}>
                {regCountdown > 0 ? `${regCountdown}s` : '获取验证码'}
              </Button>
            </div>
          </Form.Item>
          <Form.Item name="password" label="密码" rules={[
            { required: true, message: '请输入密码' },
            { min: 6, message: '密码至少6位' },
          ]}>
            <Input.Password prefix={<LockOutlined />} placeholder="密码（至少6位）" />
          </Form.Item>
          <Button type="primary" block loading={regLoading} onClick={handleRegister} style={{ height: 40 }}>
            注册并登录
          </Button>
        </Form>
      </Modal>
    </div>
  )
}
