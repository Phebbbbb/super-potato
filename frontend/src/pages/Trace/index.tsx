import { useState } from 'react'
import { Card, Input, Button, Space, Timeline, Tag, App, Typography, QRCode, Spin, Empty } from 'antd'
import { SearchOutlined, QrcodeOutlined, PrinterOutlined } from '@ant-design/icons'
import { qrApi } from '@/services/api'

const { Text, Paragraph } = Typography

const STAGE_MAP: Record<string, { color: string; text: string }> = {
  ingest: { color: 'blue', text: '票据入库' },
  ai_voucher: { color: 'purple', text: 'AI 记账' },
  confirm: { color: 'green', text: '审核确认' },
  file_tax: { color: 'orange', text: '纳税申报' },
  report: { color: 'cyan', text: '报表生成' },
}

export default function Trace() {
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [chain, setChain] = useState<any[] | null>(null)
  const [error, setError] = useState('')
  const { message } = App.useApp()

  const handleSearch = async () => {
    const q = query.trim()
    if (!q) { message.warning('请输入凭证编号或 QR 码 ID'); return }
    setLoading(true)
    setError('')
    setChain(null)

    try {
      let result: any
      if (/^[a-f0-9-]{36}$/i.test(q) || /^[a-f0-9]{32}$/i.test(q)) {
        result = await qrApi.scan(q)
      } else if (q.includes(':')) {
        const [type, id] = q.split(':')
        result = await qrApi.trace(type, id)
      } else {
        result = await qrApi.trace('voucher', q)
      }
      const items = (result as any)?.chain || (result as any)?.items || (Array.isArray(result) ? result : [])
      if (items.length === 0) {
        setError('未找到追溯记录')
      } else {
        setChain(items)
      }
    } catch {
      setError('查询失败，请检查输入')
    }
    setLoading(false)
  }

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h2>QR 全链路追溯</h2>
        <Text type="secondary">输入凭证编号、QR 码 ID 或 "voucher:ID" 格式查询完整流转时间线</Text>
      </div>

      <Card style={{ marginBottom: 24 }}>
        <Space.Compact style={{ width: 500 }}>
          <Input placeholder="输入凭证编号 / QR码ID / voucher:uuid" value={query}
            onPressEnter={handleSearch} onChange={e => setQuery(e.target.value)}
            prefix={<SearchOutlined />} />
          <Button type="primary" icon={<SearchOutlined />} onClick={handleSearch} loading={loading}>追溯查询</Button>
        </Space.Compact>
        <Button style={{ marginLeft: 12 }} icon={<PrinterOutlined />}
          onClick={() => {
            if (chain && chain.length > 0) {
              const w = window.open('', '_blank', 'width=600,height=400')
              if (w) {
                w.document.write(`<html><head><title>QR追溯打印</title><style>body{font-family:sans-serif;padding:20px} .node{border-left:3px solid #1677ff;padding:8px 16px;margin:8px 0} .time{color:#999;font-size:12px}</style></head><body><h2>QR追溯链</h2>${chain.map((n:any)=>`<div class="node"><strong>${n.stage||n.action}</strong> — ${n.description||''}<div class="time">${n.created_at||''}</div></div>`).join('')}<script>window.print()</script></body></html>`)
                w.document.close()
              }
            } else {
              message.info('请先查询凭证或QR码后再打印')
            }
          }}>
          打印追溯链
        </Button>
      </Card>

      {loading && <Spin style={{ display: 'block', margin: '40px auto' }} />}

      {error && <Card><Empty description={error} /></Card>}

      {chain && chain.length > 0 && (
        <Card title={`追溯链 — 共 ${chain.length} 个环节`} style={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
          <Timeline
            items={chain.map((item: any, i: number) => {
              const stage = STAGE_MAP[item.stage] || { color: 'default', text: item.stage }
              return {
                color: stage.color,
                children: (
                  <div style={{ display: 'flex', gap: 20, alignItems: 'flex-start' }}>
                    <div style={{ flex: 1 }}>
                      <Space style={{ marginBottom: 8 }}>
                        <Tag color={stage.color}>{stage.text}</Tag>
                        <Text type="secondary">{item.created_at?.slice(0, 19)}</Text>
                        {i === chain.length - 1 && <Tag color="green">当前</Tag>}
                      </Space>
                      <Paragraph style={{ margin: 0, fontSize: 13 }}>
                        <Text>目标类型：{item.target_type}</Text><br />
                        <Text>目标 ID：{item.target_id}</Text><br />
                        {item.scan_url && <Text>扫码链接：{item.scan_url}</Text>}
                      </Paragraph>
                    </div>
                    {item.qr_code_path && (
                      <QRCode value={item.scan_url || `${window.location.origin}/api/qr/scan/${item.id}/page`}
                        size={100} bordered={false} />
                    )}
                  </div>
                ),
              }
            })}
          />
        </Card>
      )}
    </div>
  )
}
