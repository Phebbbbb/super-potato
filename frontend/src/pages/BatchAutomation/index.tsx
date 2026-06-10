import { useState } from 'react'
import { Card, Button, Space, App, Typography, Tag, Select, Table, Statistic, Row, Col, Descriptions, Result, Spin, Divider } from 'antd'
import { ThunderboltOutlined, FileTextOutlined, FileProtectOutlined, ReloadOutlined } from '@ant-design/icons'
import { batchApi } from '@/services/api'
import { useClient } from '@/contexts/ClientContext'

const { Text } = Typography

export default function BatchAutomation() {
  const { message } = App.useApp()
  const { clientList } = useClient()
  const [operation, setOperation] = useState('filing')
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<any>(null)
  const [jobId, setJobId] = useState('')
  const [jobLoading, setJobLoading] = useState(false)
  const [poolStats, setPoolStats] = useState<any>(null)

  const handleRun = async () => {
    setRunning(true)
    setResult(null)
    try {
      const res: any = await batchApi.batchAllClients(operation)
      setResult(res)
      if (res.results?.filing?.job_id) setJobId(res.results.filing.job_id)
      if (res.results?.invoice?.job_id) setJobId(res.results.invoice.job_id)
      const totalSuccess = (res.results?.filing?.success || 0) + (res.results?.invoice?.success || 0)
      const totalFailed = (res.results?.filing?.failed || 0) + (res.results?.invoice?.failed || 0)
      if (totalSuccess > 0) message.success(`批量完成：${totalSuccess} 成功，${totalFailed} 失败`)
      else message.info('没有待处理项')
    } catch { message.error('批量操作失败') }
    setRunning(false)
  }

  const handleQueryJob = async () => {
    if (!jobId) return
    setJobLoading(true)
    try {
      const res: any = await batchApi.getJobStatus(jobId)
      setResult((prev: any) => ({ ...prev, job: res }))
    } catch { message.error('查询失败') }
    setJobLoading(false)
  }

  const handlePoolStats = async () => {
    try {
      const res: any = await batchApi.poolStats()
      setPoolStats(res)
    } catch { /* */ }
  }

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h2 style={{ margin: 0 }}>批量自动化</h2>
        <Text type="secondary">一键对全部活跃客户执行批量申报/批量开票</Text>
      </div>

      <Card style={{ marginBottom: 16 }}>
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <Space>
            <Select value={operation} onChange={setOperation} style={{ width: 180 }}
              options={[
                { label: '批量申报', value: 'filing' },
                { label: '批量开票', value: 'invoice' },
                { label: '申报+开票', value: 'both' },
              ]} />
            <Button type="primary" icon={<ThunderboltOutlined />} loading={running} onClick={handleRun} danger>
              执行全客户批量操作
            </Button>
          </Space>
          <Text type="secondary">
            {operation === 'filing' && '扫描所有活跃客户的待申报项，并行提交至电子税务局'}
            {operation === 'invoice' && '扫描所有活跃客户的草稿发票，并行开具数电票'}
            {operation === 'both' && '先批量申报所有客户，再批量开票'}
          </Text>
        </Space>
      </Card>

      {result && (
        <Card title="执行结果" style={{ marginBottom: 16 }}>
          <Descriptions column={3} bordered size="small">
            <Descriptions.Item label="操作类型">{result.operation}</Descriptions.Item>
            <Descriptions.Item label="客户数">{result.clients_count}</Descriptions.Item>
          </Descriptions>
          {result.results?.filing && (
            <>
              <Divider orientation="left" plain>申报</Divider>
              <Row gutter={16}>
                <Col span={6}><Statistic title="总数" value={result.results.filing.total} /></Col>
                <Col span={6}><Statistic title="成功" value={result.results.filing.success} valueStyle={{ color: 'green' }} /></Col>
                <Col span={6}><Statistic title="失败" value={result.results.filing.failed} valueStyle={{ color: 'red' }} /></Col>
                <Col span={6}><Statistic title="任务ID" value={result.results.filing.job_id?.slice(0, 8) || '-'} /></Col>
              </Row>
            </>
          )}
          {result.results?.invoice && (
            <>
              <Divider orientation="left" plain>开票</Divider>
              <Row gutter={16}>
                <Col span={6}><Statistic title="总数" value={result.results.invoice.total} /></Col>
                <Col span={6}><Statistic title="成功" value={result.results.invoice.success} valueStyle={{ color: 'green' }} /></Col>
                <Col span={6}><Statistic title="失败" value={result.results.invoice.failed} valueStyle={{ color: 'red' }} /></Col>
              </Row>
            </>
          )}
          {result.results?.filing?.job_id && (
            <div style={{ marginTop: 12 }}>
              <Button icon={<ReloadOutlined />} loading={jobLoading} onClick={handleQueryJob}>查询任务详情</Button>
            </div>
          )}
        </Card>
      )}

      <Card title="引擎池状态" extra={<Button icon={<ReloadOutlined />} onClick={handlePoolStats}>刷新</Button>}>
        {poolStats ? (
          <Descriptions column={3} size="small">
            <Descriptions.Item label="池大小">{poolStats.pool_size}</Descriptions.Item>
            <Descriptions.Item label="无头模式">{poolStats.headless ? '是' : '否'}</Descriptions.Item>
            <Descriptions.Item label="申报引擎">{poolStats.engines?.filing || '-'}</Descriptions.Item>
            <Descriptions.Item label="开票引擎">{poolStats.engines?.invoice || '-'}</Descriptions.Item>
          </Descriptions>
        ) : (
          <Text type="secondary">点击刷新查看引擎池状态</Text>
        )}
      </Card>
    </div>
  )
}
