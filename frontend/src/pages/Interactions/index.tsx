import { useState, useEffect, useCallback } from 'react'
import { Card, List, Typography, Tag, Button, Form, Input, App, Empty, Space, Badge, Modal, Select, Avatar } from 'antd'
import { MessageOutlined, SendOutlined, CustomerServiceOutlined, ReloadOutlined, SoundOutlined, LinkOutlined, UserOutlined, WechatOutlined } from '@ant-design/icons'
import { interactionApi, notificationApi, announcementApi, clientApi, wechatApi } from '@/services/api'
import { useClient } from '@/contexts/ClientContext'
import dayjs from 'dayjs'

const { Text, Paragraph } = Typography
const { TextArea } = Input

// ===== 政策公告 Tab =====
function AnnouncementTab() {
  const { message } = App.useApp()
  const [items, setItems] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [refreshing, setRefreshing] = useState(false)

  const fetch = async () => {
    setLoading(true)
    try {
      const res: any = await announcementApi.list(50)
      setItems(res.items || [])
    } catch { /* ignore */ }
    setLoading(false)
  }

  useEffect(() => { fetch() }, [])

  const refresh = async () => {
    setRefreshing(true)
    try {
      const res: any = await announcementApi.refresh()
      message.success(res.message || '刷新完成')
      fetch()
    } catch { message.error('刷新失败') }
    setRefreshing(false)
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h2 style={{ margin: 0 }}>
          <SoundOutlined style={{ marginRight: 8, color: '#dc2626' }} />
          国家税务总局政策公告
        </h2>
        <Button icon={<ReloadOutlined />} onClick={refresh} loading={refreshing}>刷新公告</Button>
      </div>
      <div style={{ marginBottom: 12, padding: '8px 14px', background: '#fef2f2', borderRadius: 6, border: '1px solid #fecaca' }}>
        <Text style={{ fontSize: 12, color: '#991b1b' }}>
          数据来源：<strong>国家税务总局官网</strong> (chinatax.gov.cn) — 最新法规文件 & 政策解读
        </Text>
      </div>
      <List
        loading={loading}
        dataSource={items}
        locale={{ emptyText: <Empty description="暂无公告，点击刷新拉取最新政策" /> }}
        renderItem={(item: any) => (
          <List.Item
            extra={<Button type="link" icon={<LinkOutlined />} href={item.url} target="_blank" rel="noopener noreferrer">查看原文</Button>}
          >
            <List.Item.Meta
              title={<Space><Tag color="red">{item.source}</Tag><Text strong style={{ fontSize: 14 }}>{item.title}</Text></Space>}
              description={<Text type="secondary" style={{ fontSize: 12 }}>{item.pub_date}</Text>}
            />
          </List.Item>
        )}
      />
    </div>
  )
}

// ===== 微信式消息中心 =====
function MessageCenter() {
  const { message } = App.useApp()
  const { currentClientId } = useClient()
  const [conversations, setConversations] = useState<any[]>([])
  const [activeConv, setActiveConv] = useState<any>(null)
  const [convMessages, setConvMessages] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [text, setText] = useState('')
  const [sending, setSending] = useState(false)
  const [feedbackOpen, setFeedbackOpen] = useState(false)
  const [feedbackForm] = Form.useForm()
  const [feedbackSending, setFeedbackSending] = useState(false)

  const userStr = localStorage.getItem('user')
  const user = userStr ? JSON.parse(userStr) : null
  const isStaff = user?.role !== 'client'

  // 微信绑定状态
  const [wechatBound, setWechatBound] = useState(false)
  const [wechatNickname, setWechatNickname] = useState('')
  const [wechatModalOpen, setWechatModalOpen] = useState(false)
  const [wechatBindLoading, setWechatBindLoading] = useState(false)
  const [wechatDevForm] = Form.useForm()

  const fetchWechatStatus = async () => {
    try {
      const res: any = await wechatApi.status()
      if (res.bound) {
        setWechatBound(true)
        setWechatNickname(res.binding?.nickname || '')
      } else {
        setWechatBound(false)
        setWechatNickname('')
      }
    } catch { /* ignore */ }
  }

  useEffect(() => { fetchWechatStatus() }, [])

  const handleWechatBind = async () => {
    setWechatBindLoading(true)
    try {
      const res: any = await wechatApi.authorizeUrl()
      if (res.is_dev) {
        // 开发模式: 直接弹窗填写模拟绑定
        setWechatModalOpen(true)
      } else {
        // 生产环境: 跳转微信授权页
        window.location.href = res.url
      }
    } catch { message.error('获取授权链接失败') }
    setWechatBindLoading(false)
  }

  const handleDevBind = async () => {
    const values = await wechatDevForm.validateFields()
    setWechatBindLoading(true)
    try {
      const res: any = await wechatApi.bind({
        openid: `dev_openid_${values.user_id || user?.id}`,
        nickname: values.nickname || `微信用户${(user?.display_name || 'U').slice(0, 4)}`,
      })
      if (res.success) {
        message.success('微信绑定成功')
        setWechatBound(true)
        setWechatNickname(values.nickname || '')
        setWechatModalOpen(false)
        wechatDevForm.resetFields()
      }
    } catch (e: any) { message.error(e?.detail || '绑定失败') }
    setWechatBindLoading(false)
  }

  const handleUnbind = async () => {
    try {
      await wechatApi.unbind()
      message.success('微信解绑成功')
      setWechatBound(false)
      setWechatNickname('')
    } catch (e: any) { message.error(e?.detail || '解绑失败') }
  }

  // 加载对话列表
  const fetchConversations = useCallback(async () => {
    setLoading(true)
    try {
      if (isStaff) {
        // 服务端: 爻管家 + 我管辖的客户对话
        const res: any = await interactionApi.serviceMessages(200)
        const msgs = res.items || []
        // 爻管家对话 (全局消息、反馈)
        const adminMsgs = msgs.filter((m: any) => !m.client_id || m.type === 'feedback')
        const clientMsgs = msgs.filter((m: any) => m.client_id)
        const conversations: any[] = []
        // 爻管家置顶
        conversations.push({
          id: 'yaoguanjia_svc',
          name: '爻管家',
          avatar: 'service',
          desc: '人工客服中心',
          lastMsg: adminMsgs[0]?.message?.slice(0, 30) || '暂无消息',
          lastTime: adminMsgs[0]?.created_at || '',
          unread: adminMsgs.filter((m: any) => !m.is_read).length,
          type: 'interaction',
        })
        // 按 client_id 分组为客户对话
        const convMap = new Map<string, any>()
        clientMsgs.forEach((m: any) => {
          if (!convMap.has(m.client_id)) {
            convMap.set(m.client_id, {
              id: m.client_id,
              clientId: m.client_id,
              name: m.client_name || m.client_id,
              avatar: 'client',
              lastMsg: '',
              lastTime: '',
              unread: 0,
              type: 'interaction',
            })
          }
          const conv = convMap.get(m.client_id)!
          if (!conv.lastTime || m.created_at > conv.lastTime) {
            conv.lastMsg = m.message?.slice(0, 30) || ''
            conv.lastTime = m.created_at
          }
          if (!m.is_read) conv.unread++
        })
        conversations.push(...Array.from(convMap.values()))
        setConversations(conversations)
        if (!activeConv) setActiveConv(conversations[0])
      } else {
        // 客户端: 获取消息，按发送者分组 → 爻管家 + 爻工 两个对话
        const res: any = await interactionApi.clientMessages(100)
        const msgs = res.items || []
        // 按 sender_name 分组
        const convMap = new Map<string, any>()
        const defaultConvs = [
          { key: 'yaoguanjia', name: '爻管家', avatar: 'service', desc: '人工客服中心' },
          { key: 'yaogong', name: '爻工', avatar: 'staff', desc: '专属会计' },
        ]
        defaultConvs.forEach(c => convMap.set(c.key, { id: c.key, name: c.name, avatar: c.avatar, desc: c.desc, lastMsg: '', lastTime: '', unread: 0, type: 'interaction' }))
        msgs.forEach((m: any) => {
          // 判断消息属于哪个对话
          const isFromAdmin = !m.sender_id || m.sender_name === '爻管家' || m.type === 'interaction'
          const isFeedback = m.type === 'feedback' || m.direction === 'out'
          let key: string
          if (isFeedback) {
            // 客户发出的反馈 → 两个对话都有
            key = 'yaoguanjia'
          } else if (isFromAdmin) {
            key = 'yaoguanjia'
          } else {
            key = 'yaogong'
          }
          const conv = convMap.get(key)!
          if (!conv.lastTime || m.created_at > conv.lastTime) {
            conv.lastMsg = m.message?.slice(0, 30) || ''
            conv.lastTime = m.created_at
          }
          if (!m.is_read) conv.unread++
        })
        // 确保两个对话都显示
        const convs = Array.from(convMap.values())
        setConversations(convs)
        setConvMessages(msgs)
        setActiveConv(convs[0])
      }
    } catch { /* ignore */ }
    setLoading(false)
  }, [isStaff])

  useEffect(() => { fetchConversations() }, [fetchConversations])

  // 点击对话加载消息
  const openConversation = async (conv: any) => {
    setActiveConv(conv)
    try {
      if (isStaff) {
        const res: any = await interactionApi.serviceMessages(200)
        const msgs = res.items || []
        if (conv.id === 'yaoguanjia_svc') {
          // 爻管家对话: 无客户归属的全局消息 + 反馈
          setConvMessages(msgs.filter((m: any) =>
            !m.client_id || m.type === 'feedback'
          ))
        } else {
          // 指定客户对话
          setConvMessages(msgs.filter((m: any) =>
            m.client_id === (conv.clientId || conv.id)
          ))
        }
      } else {
        // 客户端: 按对话过滤消息
        const res: any = await interactionApi.clientMessages(100)
        const msgs = res.items || []
        if (conv.id === 'yaoguanjia') {
          // 爻管家对话: 显示系统消息 + admin发来的消息 + 自己的反馈
          setConvMessages(msgs.filter((m: any) =>
            m.type === 'interaction' || m.sender_name === '爻管家' || !m.sender_id || m.direction === 'out'
          ))
        } else {
          // 爻工对话: 显示有具体 sender_id 的消息
          setConvMessages(msgs.filter((m: any) =>
            m.sender_id && m.sender_name !== '爻管家' && m.type === 'interaction'
          ))
        }
      }
    } catch { /* ignore */ }
  }

  // 发送消息
  const handleSend = async () => {
    if (!text.trim()) return
    setSending(true)
    try {
      if (isStaff && activeConv) {
        if (activeConv.id === 'yaoguanjia_svc') {
          message.warning('请在左侧选择具体客户发送消息')
          setSending(false)
          return
        }
        await interactionApi.sendToClient({
          client_id: activeConv.clientId || activeConv.id,
          title: '客服消息',
          message: text,
        })
      } else {
        await interactionApi.feedback({
          title: '反馈',
          message: text,
        })
      }
      message.success('发送成功')
      setText('')
      fetchConversations()
      if (activeConv) openConversation(activeConv)
    } catch { message.error('发送失败') }
    setSending(false)
  }

  // 发送反馈
  const handleFeedback = async () => {
    try {
      const values = await feedbackForm.validateFields()
      setFeedbackSending(true)
      await interactionApi.feedback({ title: values.title, message: values.message })
      message.success('反馈已送达爻管家')
      feedbackForm.resetFields()
      setFeedbackOpen(false)
      fetchConversations()
    } catch (e: any) {
      if (e?.errorFields) return
      message.error('发送失败')
    }
    setFeedbackSending(false)
  }

  const TYPE_TAG: Record<string, { color: string; label: string }> = {
    feedback: { color: 'purple', label: '反馈' },
    interaction: { color: 'blue', label: '客服' },
    deadline: { color: 'orange', label: '提醒' },
    rpa: { color: 'green', label: 'RPA' },
  }

  return (
    <div style={{ display: 'flex', height: 'calc(100vh - 200px)', minHeight: 500, gap: 0 }}>
      {/* ===== 左侧对话列表 (微信式) ===== */}
      <div style={{
        width: 300, minWidth: 300, borderRight: '1px solid #e5e7eb',
        display: 'flex', flexDirection: 'column', background: '#fafafa',
      }}>
        <div style={{ padding: '12px 16px', borderBottom: '1px solid #e5e7eb', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 4 }}>
          <Text strong style={{ fontSize: 15 }}>
            <WechatOutlined style={{ marginRight: 6, color: wechatBound ? '#07c160' : '#94a3b8' }} />
            消息
            {wechatBound && (
              <Tag color="green" style={{ marginLeft: 6, fontSize: 10, lineHeight: '16px' }}>
                微信已绑定
              </Tag>
            )}
          </Text>
          <Space size={4}>
            {wechatBound ? (
              <Button size="small" type="text" danger onClick={handleUnbind} style={{ fontSize: 11 }}>
                解绑微信
              </Button>
            ) : (
              <Button size="small" type="link" icon={<WechatOutlined />} onClick={handleWechatBind}
                loading={wechatBindLoading} style={{ fontSize: 11, color: '#07c160' }}>
                绑定微信
              </Button>
            )}
            {!isStaff && (
              <Button size="small" type="primary" icon={<MessageOutlined />}
                onClick={() => setFeedbackOpen(true)}
                style={{ background: '#07c160', borderColor: '#07c160', fontSize: 12 }}>
                反馈
              </Button>
            )}
            <Button size="small" type="text" icon={<ReloadOutlined />} onClick={fetchConversations} />
          </Space>
        </div>
        <div style={{ flex: 1, overflow: 'auto' }}>
          {conversations.length === 0 ? (
            <div style={{ padding: 40, textAlign: 'center', color: '#94a3b8' }}>
              <MessageOutlined style={{ fontSize: 32, marginBottom: 8 }} />
              <div style={{ fontSize: 12 }}>{isStaff ? '选择客户开始对话' : '暂无消息'}</div>
            </div>
          ) : (
            conversations.map((conv: any) => {
              const typeInfo = TYPE_TAG[conv.type] || { color: 'default', label: conv.type }
              return (
                <div
                  key={conv.id}
                  onClick={() => openConversation(conv)}
                  style={{
                    padding: '12px 16px', cursor: 'pointer',
                    background: activeConv?.id === conv.id ? '#e8f4e8' : 'transparent',
                    borderBottom: '1px solid #f0f0f0',
                    transition: 'background 0.15s',
                  }}
                  onMouseEnter={e => { if (activeConv?.id !== conv.id) e.currentTarget.style.background = '#f5f5f5' }}
                  onMouseLeave={e => { if (activeConv?.id !== conv.id) e.currentTarget.style.background = 'transparent' }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <Badge dot={conv.unread > 0}>
                      <Avatar icon={<UserOutlined />}
                        style={{ background: conv.avatar === 'service' ? '#07c160' : '#1677ff' }} />
                    </Badge>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <Text strong style={{ fontSize: 14 }}>{conv.name}</Text>
                        <Text type="secondary" style={{ fontSize: 11 }}>
                          {conv.lastTime ? dayjs(conv.lastTime).format('HH:mm') : ''}
                        </Text>
                      </div>
                      {conv.desc && (
                        <Text type="secondary" style={{ fontSize: 11, display: 'block' }}>{conv.desc}</Text>
                      )}
                      <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                        <Tag color={typeInfo.color} style={{ fontSize: 10, lineHeight: '16px', padding: '0 4px' }}>
                          {typeInfo.label}
                        </Tag>
                        <Text type="secondary" style={{ fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {conv.lastMsg}
                        </Text>
                      </div>
                    </div>
                  </div>
                </div>
              )
            })
          )}
        </div>
      </div>

      {/* ===== 右侧聊天面板 (微信式) ===== */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: '#f5f5f5' }}>
        {activeConv ? (
          <>
            {/* 聊天头部 */}
            <div style={{
              padding: '10px 16px', background: '#fff', borderBottom: '1px solid #e5e7eb',
              display: 'flex', alignItems: 'center', gap: 8,
            }}>
              <Avatar icon={<UserOutlined />}
                style={{ background: activeConv.avatar === 'service' ? '#07c160' : '#1677ff' }} />
              <div>
                <Text strong style={{ fontSize: 14 }}>{activeConv.name}</Text>
                {activeConv.desc && (
                  <div style={{ fontSize: 11, color: '#94a3b8' }}>{activeConv.desc}</div>
                )}
              </div>
            </div>

            {/* 消息列表 (气泡式) */}
            <div style={{
              flex: 1, overflow: 'auto', padding: '16px',
              display: 'flex', flexDirection: 'column', gap: 12,
            }}>
              {convMessages.length === 0 ? (
                <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Empty description="暂无消息记录" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                </div>
              ) : (
                convMessages.map((m: any) => {
                  const isMine = isStaff ? m.direction === 'out' : m.type === 'feedback'
                  const typeInfo = TYPE_TAG[m.type] || { color: 'default', label: m.type }
                  const showSender = !isMine && m.sender_name && !isStaff
                  const senderIsAdmin = showSender && (m.sender_name === '爻管家' || !m.sender_id)
                  return (
                    <div key={m.id} style={{
                      display: 'flex', flexDirection: 'column',
                      alignItems: isMine ? 'flex-end' : 'flex-start',
                    }}>
                      {/* 发送者名称（客户端显示） */}
                      {showSender && (
                        <Text style={{ fontSize: 11, padding: '0 4px', marginBottom: 2, color: senderIsAdmin ? '#7c3aed' : '#2563eb', fontWeight: 500 }}>
                          {m.sender_name}
                        </Text>
                      )}
                      {/* 时间戳 */}
                      <Text type="secondary" style={{ fontSize: 10, marginBottom: 2, padding: '0 4px' }}>
                        {m.created_at ? dayjs(m.created_at).format('MM-DD HH:mm') : ''}
                      </Text>
                      {/* 气泡 */}
                      <div style={{
                        maxWidth: '70%', padding: '10px 14px',
                        borderRadius: isMine ? '16px 4px 16px 16px' : '4px 16px 16px 16px',
                        background: isMine ? '#95ec69' : '#fff',
                        boxShadow: '0 1px 2px rgba(0,0,0,0.06)',
                        wordBreak: 'break-word',
                      }}>
                        {m.title && m.title !== '客服消息' && m.title !== '反馈' && (
                          <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 4, color: '#374151' }}>
                            <Tag color={typeInfo.color} style={{ fontSize: 10, lineHeight: '16px', padding: '0 3px' }}>
                              {typeInfo.label}
                            </Tag>
                            {m.title}
                          </div>
                        )}
                        <Text style={{ fontSize: 13, color: '#1f2937' }}>{m.message}</Text>
                      </div>
                    </div>
                  )
                })
              )}
            </div>

            {/* 输入区域 (微信式) */}
            <div style={{
              padding: '12px 16px', background: '#fff', borderTop: '1px solid #e5e7eb',
              display: 'flex', gap: 8, alignItems: 'flex-end',
            }}>
              <Input.TextArea
                value={text}
                onChange={e => setText(e.target.value)}
                onPressEnter={e => {
                  if (!e.shiftKey) { e.preventDefault(); handleSend() }
                }}
                placeholder={isStaff ? (activeConv?.id === 'yaoguanjia_svc' ? '选择左侧客户发送消息...' : '输入消息...') : '反馈爻管家...'}
                autoSize={{ minRows: 1, maxRows: 4 }}
                style={{ flex: 1, borderRadius: 8 }}
              />
              <Button
                type="primary"
                icon={<SendOutlined />}
                onClick={handleSend}
                loading={sending}
                disabled={!text.trim() || (isStaff && activeConv?.id === 'yaoguanjia_svc')}
                style={{ background: '#07c160', borderColor: '#07c160', borderRadius: 8 }}
              />
            </div>
          </>
        ) : (
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ textAlign: 'center', color: '#94a3b8' }}>
              <WechatOutlined style={{ fontSize: 48, color: '#07c160', marginBottom: 12 }} />
              <div style={{ fontSize: 14 }}>选择左侧对话开始聊天</div>
            </div>
          </div>
        )}
      </div>

      {/* 微信绑定弹窗 */}
      <Modal
        title={<Space><WechatOutlined style={{ color: '#07c160' }} />绑定微信</Space>}
        open={wechatModalOpen}
        onCancel={() => { setWechatModalOpen(false); wechatDevForm.resetFields() }}
        onOk={handleDevBind}
        confirmLoading={wechatBindLoading}
        okText="确认绑定"
      >
        <div style={{ marginBottom: 12, padding: '8px 12px', background: '#f0fff4', borderRadius: 6, fontSize: 12, color: '#166534', border: '1px solid #bbf7d0' }}>
          开发模式：直接填写信息完成模拟绑定
        </div>
        <Form form={wechatDevForm} layout="vertical">
          <Form.Item name="user_id" label="用户标识">
            <Input placeholder="模拟 openid 后缀（可选）" />
          </Form.Item>
          <Form.Item name="nickname" label="微信昵称" rules={[{ required: true, message: '请输入微信昵称' }]}>
            <Input placeholder="如：张会计" maxLength={30} />
          </Form.Item>
        </Form>
      </Modal>

      {/* 反馈弹窗 */}
      <Modal
        title={<Space><MessageOutlined style={{ color: '#7c3aed' }} />反馈爻管家</Space>}
        open={feedbackOpen}
        onCancel={() => { setFeedbackOpen(false); feedbackForm.resetFields() }}
        onOk={handleFeedback}
        confirmLoading={feedbackSending}
        okText="发送反馈"
      >
        <div style={{ marginBottom: 12, padding: '8px 12px', background: '#f5f3ff', borderRadius: 6, fontSize: 12, color: '#7c3aed' }}>
          您的反馈将直达 <strong>爻管家</strong>（总管理员）
        </div>
        <Form form={feedbackForm} layout="vertical">
          <Form.Item name="title" label="反馈主题" rules={[{ required: true, message: '请输入主题' }]}>
            <Input placeholder="如：发票开具问题" />
          </Form.Item>
          <Form.Item name="message" label="详细描述" rules={[{ required: true, message: '请输入描述' }]}>
            <TextArea rows={4} placeholder="请详细描述您的问题或反馈..." />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

export default function Interactions() {
  return (
    <div>
      <Card size="small" title="消息中心" style={{ marginBottom: 16 }}>
        <MessageCenter />
      </Card>
      <Card size="small" title="政策公告">
        <AnnouncementTab />
      </Card>
    </div>
  )
}
