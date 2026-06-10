import { useState } from 'react'
import { Card, Button, DatePicker, Select, App, Typography, Result, Spin, Tag, Space, Alert, Progress, Table, Collapse, Descriptions } from 'antd'
import { LockOutlined, CheckCircleOutlined, WarningOutlined, CloseCircleOutlined, SafetyCertificateOutlined, SearchOutlined } from '@ant-design/icons'
import { rpaApi } from '@/services/api'
import { useClient } from '@/contexts/ClientContext'
import dayjs from 'dayjs'

const { Text, Title } = Typography

const gradeConfig: Record<string, { color: string; text: string }> = {
  excellent: { color: '#16a34a', text: '优秀' },
  good: { color: '#2563eb', text: '良好' },
  warning: { color: '#d97706', text: '关注' },
  danger: { color: '#dc2626', text: '危险' },
}

export default function PeriodClose() {
  const [period, setPeriod] = useState(dayjs().format('YYYY-MM'))
  const [loading, setLoading] = useState(false)
  const [riskLoading, setRiskLoading] = useState(false)
  const [riskResult, setRiskResult] = useState<any>(null)
  const [closeResult, setCloseResult] = useState<any>(null)
  const [done, setDone] = useState(false)
  const { clientList, currentClientId } = useClient()
  const { message } = App.useApp()
  const [clientId, setClientId] = useState(currentClientId || '')

  const handleRiskCheck = async () => {
    if (!clientId) { message.warning('请选择客户'); return }
    setRiskLoading(true)
    setRiskResult(null)
    try {
      const res: any = await rpaApi.periodCloseRiskCheck(clientId, period)
      setRiskResult(res)
      if (res.can_close) {
        message.success(`风险检测通过 — 得分 ${res.score}/${res.max_score}，可安全关账`)
      } else {
        message.warning(`发现 ${res.blocker_count} 项阻断问题，需解决后才能关账`)
      }
    } catch (e: any) { message.error(e?.response?.data?.detail || '风险检测失败') }
    setRiskLoading(false)
  }

  const handleClose = async () => {
    if (!clientId) { message.warning('请选择客户'); return }
    if (riskResult && !riskResult.can_close) {
      message.error('存在阻断问题，请先解决后再执行关账')
      return
    }
    setLoading(true)
    setDone(false)
    try {
      const res: any = await rpaApi.periodClose(clientId, period)
      setCloseResult(res)
      setDone(true)
      message.success(res.message || '期末结转完成')
    } catch { message.error('期末结转失败') }
    setLoading(false)
  }

  const severityTag = (s: string) => {
    if (s === 'blocker') return <Tag color="red">阻断</Tag>
    if (s === 'warning') return <Tag color="orange">预警</Tag>
    return <Tag color="green">通过</Tag>
  }

  const statusIcon = (s: string) => {
    if (s === 'blocker') return <CloseCircleOutlined style={{ color: '#dc2626' }} />
    if (s === 'warning') return <WarningOutlined style={{ color: '#d97706' }} />
    return <CheckCircleOutlined style={{ color: '#16a34a' }} />
  }

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h2 style={{ margin: 0 }}>期末自动结转</h2>
        <Text type="secondary">一键完成当期损益结转、计提折旧、税金计提等期末处理</Text>
      </div>

      <Alert
        message="操作流程说明"
        description="第一步：执行风险检测，系统自动扫描 20 项结账前风险。第二步：确认无阻断问题后，执行期末结转。结转将自动生成记账凭证（折旧、收入结转、费用结转、税金计提等），状态为待复核。"
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
      />

      {/* 选择区 */}
      <Card style={{ marginBottom: 16 }}>
        <Space wrap>
          <Select
            placeholder="选择客户"
            value={clientId || undefined}
            onChange={(v) => setClientId(v)}
            style={{ width: 220 }}
            options={clientList.map(c => ({ label: c.name, value: c.id }))}
          />
          <DatePicker picker="month" value={dayjs(period, 'YYYY-MM')} onChange={(d) => d && setPeriod(d.format('YYYY-MM'))} />
          <Button icon={<SearchOutlined />} loading={riskLoading} onClick={handleRiskCheck}>
            风险检测
          </Button>
          <Button type="primary" icon={<LockOutlined />} loading={loading}
            onClick={handleClose}
            disabled={!riskResult || (riskResult && !riskResult.can_close)}>
            执行期末结转
          </Button>
        </Space>
      </Card>

      {/* 风险检测结果 */}
      {riskResult && (
        <Card title={<span><SafetyCertificateOutlined /> 结账风险检测结果</span>} style={{ marginBottom: 16 }}
          extra={
            <Space>
              <Tag color={gradeConfig[riskResult.grade]?.color}>{gradeConfig[riskResult.grade]?.text}</Tag>
              {riskResult.can_close
                ? <Tag color="green">可关账</Tag>
                : <Tag color="red">不可关账 — 需先解决阻断问题</Tag>
              }
            </Space>
          }>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr 1fr', gap: 16, marginBottom: 16 }}>
            <Card size="small" style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 32, fontWeight: 700, color: riskResult.score >= 85 ? '#16a34a' : riskResult.score >= 70 ? '#2563eb' : riskResult.score >= 50 ? '#d97706' : '#dc2626' }}>
                {riskResult.score}
              </div>
              <Text type="secondary">/ {riskResult.max_score} 分</Text>
            </Card>
            <Card size="small" style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 28, fontWeight: 700, color: '#16a34a' }}>{riskResult.passed_count}</div>
              <Text type="secondary">通过</Text>
            </Card>
            <Card size="small" style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 28, fontWeight: 700, color: '#d97706' }}>{riskResult.warning_count}</div>
              <Text type="secondary">预警</Text>
            </Card>
            <Card size="small" style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 28, fontWeight: 700, color: '#dc2626' }}>{riskResult.blocker_count}</div>
              <Text type="secondary">阻断</Text>
            </Card>
            <Card size="small" style={{ textAlign: 'center' }}>
              <Progress type="circle" percent={Math.round(riskResult.score / riskResult.max_score * 100)} size={48}
                strokeColor={gradeConfig[riskResult.grade]?.color} />
            </Card>
          </div>

          {/* 推荐建议 */}
          {riskResult.recommendations?.length > 0 && (
            <Alert
              type={riskResult.can_close ? 'success' : 'warning'}
              message={riskResult.recommendations.join('；')}
              style={{ marginBottom: 16 }}
              showIcon
            />
          )}

          {/* 检查项列表 */}
          <Table
            dataSource={riskResult.check_items || []}
            rowKey="check"
            size="small"
            pagination={false}
            columns={[
              { title: '检查项', dataIndex: 'check', width: 140, render: (c: string, r: any) => <Space>{statusIcon(r.status)}{c}</Space> },
              { title: '状态', dataIndex: 'status', width: 90, render: (s: string) => severityTag(s) },
              { title: '详情', dataIndex: 'detail', ellipsis: true },
            ]}
          />
        </Card>
      )}

      {/* 执行加载 */}
      {loading && <Spin style={{ display: 'block', margin: '40px auto' }} />}

      {/* 关账结果 */}
      {done && !loading && (
        <Result
          status={closeResult?.success ? 'success' : 'info'}
          title={closeResult?.success ? '期末结转已完成' : '无需结转'}
          subTitle={`期间 ${closeResult?.period || period} · 收入 ¥${closeResult?.summary?.total_revenue?.toLocaleString?.() || 0} · 费用 ¥${closeResult?.summary?.total_expense?.toLocaleString?.() || 0}`}
        >
          {closeResult?.step_log && (
            <Collapse style={{ maxWidth: 600, margin: '0 auto', textAlign: 'left' }} size="small"
              items={[{
                key: 'steps',
                label: `执行步骤 (${closeResult.step_log.length})`,
                children: (
                  <Table
                    dataSource={closeResult.step_log}
                    rowKey="step"
                    size="small"
                    pagination={false}
                    columns={[
                      { title: '步骤', dataIndex: 'step', width: 100 },
                      {
                        title: '状态', dataIndex: 'status', width: 70,
                        render: (s: string) => {
                          if (s === 'ok') return <Tag color="green">成功</Tag>
                          if (s === 'skip') return <Tag>跳过</Tag>
                          return <Tag color="red">失败</Tag>
                        },
                      },
                      { title: '详情', dataIndex: 'detail', ellipsis: true },
                    ]}
                  />
                ),
              }]}
            />
          )}
          {closeResult?.entries_generated > 0 && (
            <Tag color="blue" style={{ fontSize: 14, padding: '4px 16px', marginTop: 16 }}>
              已生成 {closeResult.entries_generated} 张结转凭证
            </Tag>
          )}
        </Result>
      )}
    </div>
  )
}
