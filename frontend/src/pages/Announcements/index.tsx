import { useState, useEffect, useCallback } from 'react'
import { Card, List, Typography, Tag, Button, App, Space, Empty, Tabs, Badge } from 'antd'
import { SoundOutlined, ReloadOutlined, LinkOutlined, SyncOutlined } from '@ant-design/icons'
import { announcementApi } from '@/services/api'

const { Text } = Typography

const SOURCE_META: Record<string, { color: string; label: string; url: string }> = {
  '国家税务总局': { color: '#dc2626', label: '国家税务总局', url: 'chinatax.gov.cn' },
  '安徽税务': { color: '#2563eb', label: '安徽税务', url: 'anhui.chinatax.gov.cn' },
  '亳州税务': { color: '#7c3aed', label: '亳州税务', url: 'anhui.chinatax.gov.cn/col/col9511' },
}

const AUTO_REFRESH_MS = 30 * 60 * 1000 // 30分钟自动刷新

export default function Announcements() {
  const { message } = App.useApp()
  const [items, setItems] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [activeSource, setActiveSource] = useState<string>('国家税务总局')
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null)

  const fetchAnnouncements = useCallback(async (source?: string) => {
    setLoading(true)
    try {
      const src = source || activeSource
      const res: any = await announcementApi.list(50, src)
      setItems(res.items || [])
    } catch { /* ignore */ }
    setLoading(false)
  }, [activeSource])

  useEffect(() => { fetchAnnouncements() }, [])

  // 定时自动刷新（每30分钟）
  useEffect(() => {
    const timer = setInterval(() => {
      fetchAnnouncements()
      setLastRefresh(new Date())
    }, AUTO_REFRESH_MS)
    return () => clearInterval(timer)
  }, [fetchAnnouncements])

  const handleRefresh = async () => {
    setRefreshing(true)
    try {
      const res: any = await announcementApi.refresh()
      message.success(res.message || '刷新完成')
      await fetchAnnouncements()
      setLastRefresh(new Date())
    } catch { message.error('刷新失败') }
    setRefreshing(false)
  }

  const handleSourceChange = (source: string) => {
    setActiveSource(source)
    fetchAnnouncements(source)
  }

  const sourceTabs = Object.entries(SOURCE_META).map(([key, meta]) => ({
    key,
    label: (
      <span>
        <Badge status="processing" style={{ marginRight: 4 }} />
        {meta.label}
      </span>
    ),
  }))

  const itemsBySource = items.filter(item => item.source === activeSource)

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h2 style={{ margin: 0 }}>
          <SoundOutlined style={{ marginRight: 8, color: '#dc2626' }} />
          官方公告
        </h2>
        <Space>
          {lastRefresh && (
            <Text type="secondary" style={{ fontSize: 11 }}>
              <SyncOutlined spin={loading} style={{ marginRight: 4 }} />
              上次刷新：{lastRefresh.toLocaleTimeString()}
            </Text>
          )}
          <Button icon={<ReloadOutlined />} onClick={handleRefresh} loading={refreshing}>
            刷新公告
          </Button>
        </Space>
      </div>

      {/* 来源切换 */}
      <Tabs
        activeKey={activeSource}
        onChange={handleSourceChange}
        items={sourceTabs}
        style={{ marginBottom: 0 }}
        tabBarStyle={{ marginBottom: 0 }}
      />

      <Card>
        <div style={{ marginBottom: 12, padding: '8px 14px', background: '#f0f9ff', borderRadius: 6, border: '1px solid #bae6fd' }}>
          <Text style={{ fontSize: 12, color: '#075985' }}>
            数据来源：<strong>{SOURCE_META[activeSource]?.label}</strong>（{SOURCE_META[activeSource]?.url}）
            &nbsp;·&nbsp; 每 30 分钟自动更新
          </Text>
        </div>

        <List
          loading={loading}
          dataSource={itemsBySource}
          locale={{ emptyText: <Empty description={`暂无${SOURCE_META[activeSource]?.label}公告，点击「刷新公告」从官网拉取最新政策`} /> }}
          renderItem={(item: any) => (
            <List.Item
              extra={
                <Button type="link" icon={<LinkOutlined />} href={item.url} target="_blank" rel="noopener noreferrer">
                  查看原文
                </Button>
              }
            >
              <List.Item.Meta
                title={
                  <Space>
                    <Tag color={SOURCE_META[item.source]?.color || 'default'}>{item.source}</Tag>
                    <Text strong style={{ fontSize: 14 }}>{item.title}</Text>
                  </Space>
                }
                description={
                  <Text type="secondary" style={{ fontSize: 12 }}>{item.pub_date}</Text>
                }
              />
            </List.Item>
          )}
        />
      </Card>
    </div>
  )
}
