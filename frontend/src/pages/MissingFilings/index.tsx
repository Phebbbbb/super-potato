import { useState } from 'react'
import { Card, Button, DatePicker, Table, Tag, Space, App, Typography, Result, Spin } from 'antd'
import { SearchOutlined, WarningOutlined } from '@ant-design/icons'
import { filingApi } from '@/services/api'
import dayjs from 'dayjs'

const { Text } = Typography

export default function MissingFilings() {
  const [period, setPeriod] = useState(dayjs().format('YYYY-MM'))
  const [loading, setLoading] = useState(false)
  const [results, setResults] = useState<any[]>([])
  const [scanned, setScanned] = useState(false)
  const { message } = App.useApp()

  const handleScan = async () => {
    setLoading(true)
    setScanned(false)
    try {
      const res: any = await filingApi.missingFilings(period)
      setResults(res.items || [])
      setScanned(true)
      if ((res.items || []).length === 0) {
        message.success(`${period} 全部申报完成，无漏报`)
      } else {
        message.warning(`发现 ${res.missing_count} 项漏报`)
      }
    } catch { message.error('扫描失败') }
    setLoading(false)
  }

  const grouped = new Map<string, any[]>()
  results.forEach(r => {
    const k = r.client_name
    if (!grouped.has(k)) grouped.set(k, [])
    grouped.get(k)!.push(r)
  })

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h2 style={{ margin: 0 }}>漏报扫描</h2>
        <Text type="secondary">自动检测所有客户指定期间内尚未申报的税种</Text>
      </div>

      <Card style={{ marginBottom: 16 }}>
        <Space>
          <DatePicker picker="month" value={dayjs(period, 'YYYY-MM')} onChange={(d) => d && setPeriod(d.format('YYYY-MM'))} />
          <Button type="primary" icon={<SearchOutlined />} loading={loading} onClick={handleScan}>
            扫描漏报
          </Button>
        </Space>
      </Card>

      {loading && <Spin style={{ display: 'block', margin: '40px auto' }} />}

      {scanned && results.length === 0 && (
        <Result status="success" title="无漏报" subTitle={`${period} 期间所有客户申报已完成`} />
      )}

      {results.length > 0 && (
        <Card title={`漏报结果 — ${results.length} 项`}>
          {Array.from(grouped.entries()).map(([clientName, items]) => (
            <Card key={clientName} size="small" title={<><WarningOutlined style={{ color: '#d97706', marginRight: 8 }} />{clientName}</>} style={{ marginBottom: 12 }}>
              <Table
                dataSource={items}
                rowKey={(r: any) => `${r.client_id}-${r.tax_type}`}
                size="small"
                pagination={false}
                columns={[
                  { title: '漏报税种', dataIndex: 'tax_name', width: 200,
                    render: (v: string) => <Tag color="red">{v}</Tag> },
                  { title: '所属期', dataIndex: 'period', width: 100 },
                  { title: '纳税人类型', dataIndex: 'taxpayer_type', width: 100,
                    render: (v: string) => v === 'general' ? '一般纳税人' : '小规模' },
                ]}
              />
            </Card>
          ))}
        </Card>
      )}
    </div>
  )
}
