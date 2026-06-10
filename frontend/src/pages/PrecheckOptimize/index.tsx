import { useState } from 'react'
import { Card, Button, Space, App, Typography, Select, Table, Tag, Statistic, Row, Col, Collapse, Descriptions, Spin, Progress } from 'antd'
import { SafetyCertificateOutlined, BulbOutlined, ThunderboltOutlined, SearchOutlined, TrophyOutlined } from '@ant-design/icons'
import { precheckApi } from '@/services/api'
import { useClient } from '@/contexts/ClientContext'

const { Text } = Typography

export default function PrecheckOptimize() {
  const { message } = App.useApp()
  const { clientList } = useClient()
  const [clientId, setClientId] = useState('')
  const [mode, setMode] = useState<'precheck' | 'optimize' | 'dp' | 'cliff'>('precheck')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<any>(null)

  const handleRun = async () => {
    if (!clientId) { message.warning('请选择客户'); return }
    setLoading(true)
    try {
      let res: any
      switch (mode) {
        case 'precheck': res = await precheckApi.check(clientId); break
        case 'optimize': res = await precheckApi.optimize(clientId); break
        case 'dp': res = await precheckApi.dpOptimize(clientId); break
        case 'cliff': res = await precheckApi.cliffCheck(clientId); break
      }
      setResult(res)
    } catch { message.error('执行失败') }
    setLoading(false)
  }

  const gradeColor: Record<string, string> = { excellent: 'green', good: 'blue', warning: 'orange', danger: 'red' }
  const gradeText: Record<string, string> = { excellent: '优秀', good: '良好', warning: '需关注', danger: '有风险' }

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h2 style={{ margin: 0 }}>预检优化</h2>
        <Text type="secondary">申报前模拟预检 + 税务优化推荐 + 多期DP全局最优路径</Text>
      </div>

      <Card style={{ marginBottom: 16 }}>
        <Space>
          <Select placeholder="选择客户" value={clientId || undefined} onChange={setClientId}
            style={{ width: 200 }} showSearch optionFilterProp="label"
            options={clientList.map(c => ({ label: c.name, value: c.id }))} />
          <Select value={mode} onChange={setMode} style={{ width: 180 }}
            options={[
              { label: '申报预检', value: 'precheck' },
              { label: '税务优化', value: 'optimize' },
              { label: '多期DP优化', value: 'dp' },
              { label: 'CIT悬崖检测', value: 'cliff' },
            ]} />
          <Button type="primary" icon={<SearchOutlined />} loading={loading} onClick={handleRun}>
            执行分析
          </Button>
        </Space>
      </Card>

      {loading && <Spin style={{ display: 'block', margin: '40px auto' }} />}

      {result && mode === 'precheck' && (
        <Card title={`预检结果 — ${result.client_name || clientId}`}>
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={6}><Statistic title="总分" value={result.score} suffix={`/ ${result.max_score || 100}`} /></Col>
            <Col span={6}><Statistic title="等级" value={gradeText[result.grade] || result.grade}
              valueStyle={{ color: gradeColor[result.grade] || 'default' }} /></Col>
            <Col span={6}><Statistic title="通过项" value={result.passed_count || 0} valueStyle={{ color: 'green' }} /></Col>
            <Col span={6}><Statistic title="问题项" value={result.failed_count || 0} valueStyle={{ color: 'red' }} /></Col>
          </Row>
          {result.checks && (
            <Table dataSource={result.checks} rowKey="name" size="small" pagination={false}
              columns={[
                { title: '检查项', dataIndex: 'name' },
                { title: '状态', dataIndex: 'passed', width: 80,
                  render: (v: boolean) => <Tag color={v ? 'green' : 'red'}>{v ? '通过' : '未通过'}</Tag> },
                { title: '详情', dataIndex: 'detail', ellipsis: true },
                { title: '建议', dataIndex: 'suggestion', ellipsis: true },
              ]} />
          )}
        </Card>
      )}

      {result && mode === 'optimize' && (
        <Card title={`税务优化建议 — ${result.client_name || clientId}`}>
          {result.recommendation && (
            <div style={{ padding: 16, background: '#f0fdf4', borderRadius: 8, marginBottom: 16, borderLeft: '3px solid #22c55e' }}>
              <BulbOutlined style={{ color: '#22c55e', marginRight: 8 }} />
              <Text strong>{result.recommendation}</Text>
            </div>
          )}
          <Row gutter={16}>
            <Col span={6}><Statistic title="潜在节税额" value={result.potential_savings} prefix="¥" valueStyle={{ color: 'green' }} /></Col>
            <Col span={6}><Statistic title="安全评分" value={result.safety_score} suffix="/100" /></Col>
          </Row>
        </Card>
      )}

      {result && mode === 'dp' && !result.error && (
        <Card title="多期 DP 全局最优路径">
          <Descriptions column={2} bordered size="small">
            <Descriptions.Item label="推荐方案">{result.recommended_scenario}</Descriptions.Item>
            <Descriptions.Item label="预计总节税">¥{(result.total_savings || 0).toLocaleString()}</Descriptions.Item>
          </Descriptions>
        </Card>
      )}

      {result && mode === 'cliff' && (
        <Card title="CIT 悬崖检测">
          <Descriptions column={2} bordered size="small">
            <Descriptions.Item label="悬崖风险等级">
              <Tag color={result.risk_level === 'high' ? 'red' : result.risk_level === 'medium' ? 'orange' : 'green'}>
                {result.risk_level || '-'}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="距悬崖阈值">¥{(result.distance_to_cliff || 0).toLocaleString()}</Descriptions.Item>
            <Descriptions.Item label="建议" span={2}>{result.recommendation || '-'}</Descriptions.Item>
          </Descriptions>
        </Card>
      )}
    </div>
  )
}
