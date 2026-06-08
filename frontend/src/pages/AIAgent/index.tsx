import { useState, useRef, useEffect } from 'react'
import { Card, Input, Button, Space, Typography, Tag, Spin } from 'antd'
import { SendOutlined, CustomerServiceOutlined, UserOutlined } from '@ant-design/icons'
import { agentApi } from '@/services/api'
import { useClient } from '@/contexts/ClientContext'

const { Text, Paragraph } = Typography

export default function AIAgent() {
  const [messages, setMessages] = useState<{ role: string; content: string }[]>([
    { role: 'assistant', content: '您好！我是 AI 税务顾问，可以帮您解答财税问题、给出记账分录建议、提示税务风险。请随时提问。' },
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const chatRef = useRef<HTMLDivElement>(null)
  const { currentClientId } = useClient()

  useEffect(() => { chatRef.current?.scrollTo(0, chatRef.current.scrollHeight) }, [messages])

  const handleSend = async () => {
    const msg = input.trim()
    if (!msg || loading) return
    setInput('')
    setMessages(prev => [...prev, { role: 'user', content: msg }])
    setLoading(true)
    try {
      const res: any = await agentApi.chat({ message: msg, client_id: currentClientId })
      setMessages(prev => [...prev, { role: 'assistant', content: res.reply || '抱歉，暂时无法回复' }])
    } catch {
      setMessages(prev => [...prev, { role: 'assistant', content: '抱歉，请求失败，请稍后重试' }])
    }
    setLoading(false)
  }

  const quickQuestions = [
    '小规模纳税人增值税起征点是多少？',
    '员工差旅费报销怎么做分录？',
    '企业所得税季度预缴如何计算？',
    '印花税有哪些税目和税率？',
  ]

  return (
    <div>
      <h2 style={{ marginBottom: 24 }}>AI 税务顾问</h2>
      <Card style={{ flex: 1, overflow: 'auto', minHeight: 0, display: 'flex', flexDirection: 'column' }}>
        <div ref={chatRef} style={{ flex: 1, overflow: 'auto', marginBottom: 16, padding: 16, background: '#f9fafb', borderRadius: 8 }}>
          {messages.map((m, i) => (
            <div key={i} style={{ display: 'flex', gap: 12, marginBottom: 16, flexDirection: m.role === 'user' ? 'row-reverse' : 'row' }}>
              <div style={{ width: 36, height: 36, borderRadius: '50%', background: m.role === 'user' ? '#1677ff' : '#52c41a', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff' }}>
                {m.role === 'user' ? <UserOutlined /> : <CustomerServiceOutlined />}
              </div>
              <div style={{ maxWidth: '70%', padding: 12, borderRadius: 8, background: m.role === 'user' ? '#1677ff' : '#fff', color: m.role === 'user' ? '#fff' : '#333', boxShadow: '0 1px 3px rgba(0,0,0,0.1)', whiteSpace: 'pre-wrap', lineHeight: 1.7 }}>
                <Text style={{ color: m.role === 'user' ? '#fff' : '#333', fontSize: 14 }}>{m.content}</Text>
              </div>
            </div>
          ))}
          {loading && <Spin style={{ display: 'block', textAlign: 'center' }} />}
        </div>

        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
          {quickQuestions.map(q => (
            <Tag key={q} color="blue" style={{ cursor: 'pointer', padding: '2px 8px' }}
              onClick={() => setInput(q)}>{q}</Tag>
          ))}
        </div>

        <Space.Compact style={{ width: '100%' }}>
          <Input.TextArea value={input} onChange={e => setInput(e.target.value)}
            onPressEnter={(e) => { e.preventDefault(); handleSend() }}
            placeholder="输入您的问题，如：小规模纳税人增值税起征点是多少？" rows={2} />
          <Button type="primary" icon={<SendOutlined />} onClick={handleSend} loading={loading}>发送</Button>
        </Space.Compact>
      </Card>
    </div>
  )
}
