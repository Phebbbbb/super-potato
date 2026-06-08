import { useState, useEffect } from 'react'
import { Card, Table, Tag, Button, Space, App, Badge, Row, Col, Statistic } from 'antd'
import { WarningOutlined, CheckCircleOutlined, ClockCircleOutlined, ReloadOutlined } from '@ant-design/icons'
import { taxApi } from '@/services/api'
import { useClient } from '@/contexts/ClientContext'

const TAX_TYPE_MAP: Record<string, string> = { vat: '增值税', individual_income: '个人所得税', corporate_income: '企业所得税', stamp_duty: '印花税' }

export default function TaxRisk() {
  const [calendar, setCalendar] = useState<any[]>([])
  const [risks, setRisks] = useState<any[]>([])
  const [score, setScore] = useState('A')
  const [loading, setLoading] = useState(false)
  const { currentClientId } = useClient()
  const { message } = App.useApp()

  const fetchData = async () => {
    setLoading(true)
    try {
      const [cRes, rRes]: any[] = await Promise.all([
        taxApi.calendar({ months_ahead: 3 }),
        taxApi.riskCheck({ client_id: currentClientId }),
      ])
      setCalendar(cRes.items || [])
      setRisks(rRes.items || [])
      setScore(rRes.score || 'A')
    } catch { message.error('加载风控数据失败') }
    setLoading(false)
  }

  useEffect(() => { fetchData() }, [currentClientId])

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 24 }}>
        <h2>税务风控</h2>
        <Button icon={<ReloadOutlined />} onClick={fetchData} loading={loading}>刷新</Button>
      </div>

      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={8}>
          <Card><Statistic title="风险评分" value={score} suffix={<Tag color={score==='A'?'green':score==='B'?'orange':'red'}>{score==='A'?'健康':score==='B'?'关注':'危险'}</Tag>} prefix={score==='A'?<CheckCircleOutlined style={{color:'green'}}/>:<WarningOutlined style={{color:'orange'}}/>} /></Card>
        </Col>
        <Col span={8}>
          <Card><Statistic title="本月待申报" value={calendar.filter(c=>!c.completed).length} suffix="项" /></Card>
        </Col>
        <Col span={8}>
          <Card><Statistic title="风险预警" value={risks.filter(r=>r.level==='A').length} suffix="条" valueStyle={{color: risks.filter(r=>r.level==='A').length>0?'red':'green'}} /></Card>
        </Col>
      </Row>

      <Row gutter={16}>
        <Col span={12}>
          <Card title={<><ClockCircleOutlined /> 申报日历</>} loading={loading} style={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
            <Table dataSource={calendar} rowKey={(r:any)=>`${r.period}-${r.tax_type}`} size="small" pagination={false}
              columns={[
                { title: '所属期', dataIndex: 'period', width: 100 },
                { title: '税种', dataIndex: 'tax_type', width: 100, render: (t:string)=>TAX_TYPE_MAP[t]||t },
                { title: '截止日期', dataIndex: 'deadline', width: 110 },
                { title: '剩余天数', dataIndex: 'days_left', width: 90, render: (d:number)=><Tag color={d<0?'red':d<=7?'orange':'blue'}>{d<0?'已逾期':`${d}天`}</Tag> },
                { title: '状态', dataIndex: 'completed', width: 80, render: (c:boolean)=>c?<Badge status="success" text="已完成"/>:<Badge status="default" text="待申报"/> },
              ]}
            />
          </Card>
        </Col>
        <Col span={12}>
          <Card title={<><WarningOutlined /> 风险预警</>} loading={loading} style={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
            <Table dataSource={risks} rowKey="type" size="small" pagination={false}
              columns={[
                { title: '等级', dataIndex: 'level', width: 60, render: (l:string)=><Tag color={l==='A'?'red':l==='B'?'orange':'blue'}>{l==='A'?'严重':l==='B'?'关注':'提示'}</Tag> },
                { title: '事项', dataIndex: 'message', width: 300 },
                { title: '建议', dataIndex: 'suggestion', width: 200, render: (s:string)=>s||'-' },
              ]}
            />
          </Card>
        </Col>
      </Row>
    </div>
  )
}
