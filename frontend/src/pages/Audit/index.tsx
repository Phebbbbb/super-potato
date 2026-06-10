import { useState, useEffect } from 'react'
import { Card, Table, Tag, Button, Space, App, Row, Col, Statistic, Modal, Input, Form, Rate, Typography, Divider, Tabs, Checkbox, Progress, Descriptions, Select, DatePicker } from 'antd'
import dayjs from 'dayjs'
import { CheckOutlined, CloseOutlined, AuditOutlined, WarningOutlined, CheckCircleOutlined, HistoryOutlined, ExportOutlined, ThunderboltOutlined, SettingOutlined } from '@ant-design/icons'
import { auditApi, voucherApi, filingApi, feedbackApi } from '@/services/api'
import { useClient } from '@/contexts/ClientContext'
import type { ColumnsType } from 'antd/es/table'

const { Text } = Typography

export default function Audit() {
  const [summary, setSummary] = useState<any>({})
  const [pendingVouchers, setPendingVouchers] = useState<any[]>([])
  const [pendingFilings, setPendingFilings] = useState<any[]>([])
  const [recentAudits, setRecentAudits] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [selectedVoucher, setSelectedVoucher] = useState<any>(null)
  const [auditScore, setAuditScore] = useState(3)
  const [auditComment, setAuditComment] = useState('')
  const { currentClientId } = useClient()
  const { message } = App.useApp()
  const userStr = localStorage.getItem('user')
  const user = userStr ? JSON.parse(userStr) : null
  const reviewer = user?.display_name || '审计员'

  const fetchAll = async () => {
    setLoading(true)
    try {
      const clientParam = { client_id: currentClientId || undefined }
      const [sRes, vRes, fRes, aRes]: any[] = await Promise.all([
        auditApi.summary(clientParam),
        auditApi.pendingVouchers(clientParam),
        filingApi.list({ page_size: 50, client_id: currentClientId || undefined }),
        auditApi.recentAudits({ limit: 50 }),
      ])
      setSummary(sRes)
      setPendingVouchers(vRes.items || [])
      setPendingFilings((fRes.items || []).filter((f: any) => f.status === 'pending' || f.status === 'pending_review'))
      setRecentAudits(aRes.items || [])
    } catch { message.error('加载内审数据失败') }
    setLoading(false)
  }

  useEffect(() => { fetchAll() }, [currentClientId])

  const handleVoucherAudit = (record: any) => {
    setSelectedVoucher(record)
    setAuditScore(3)
    setAuditComment('')
    setConfirmOpen(true)
  }

  const handleVoucherConfirm = async () => {
    try {
      await voucherApi.confirm(selectedVoucher.id, { reviewer: reviewer, comment: `[内审评分:${auditScore}/5] ${auditComment}` })
      message.success('凭证审核通过')
      setConfirmOpen(false)
      fetchAll()
    } catch (e: any) { message.error(e?.response?.data?.detail || '审核失败') }
  }

  const handleVoucherReject = async (record: any) => {
    Modal.confirm({
      title: '驳回凭证',
      icon: <WarningOutlined />,
      content: <Input.TextArea id="audit-reject-reason" placeholder="请输入驳回原因" rows={3} />,
      onOk: async () => {
        const reason = (document.getElementById('audit-reject-reason') as HTMLTextAreaElement)?.value || '内审驳回'
        try {
          await feedbackApi.rejectVoucher(record.id, { reason, issues: [reason] })
          message.success('凭证已驳回')
          fetchAll()
        } catch (e: any) { message.error(e?.response?.data?.detail || '驳回失败') }
      },
    })
  }

  const handleFilingApprove = async (record: any) => {
    try {
      await feedbackApi.reviewFiling(record.id, { action: 'approve', comment: '内审通过，提交申报', reviewer: reviewer })
      message.success('申报已审核通过')
      fetchAll()
    } catch (e: any) { message.error(e?.response?.data?.detail || '审核失败') }
  }

  const handleFilingReject = async (record: any) => {
    Modal.confirm({
      title: '驳回申报',
      content: <Input.TextArea id="filing-reject-reason" placeholder="请输入驳回原因" rows={3} />,
      onOk: async () => {
        const reason = (document.getElementById('filing-reject-reason') as HTMLTextAreaElement)?.value || '内审驳回'
        try {
          await feedbackApi.reviewFiling(record.id, { action: 'reject', comment: reason, reviewer: reviewer })
          message.success('申报已驳回')
          fetchAll()
        } catch (e: any) { message.error(e?.response?.data?.detail || '驳回失败') }
      },
    })
  }

  const handleExportReport = () => {
    const rows = recentAudits.map((a: any) => ({
      时间: a.created_at?.slice(0, 19) || '',
      对象类型: a.target_type,
      对象ID: a.target_id,
      操作: a.action,
      操作人: a.operator,
      详情: typeof a.detail === 'string' ? a.detail : JSON.stringify(a.detail || ''),
    }))
    let csv = '﻿时间,对象类型,对象ID,操作,操作人,详情\n'
    rows.forEach(r => { csv += Object.values(r).map(v => { const s = String(v).replace(/"/g, '""'); return s.includes(',') ? `"${s}"` : s }).join(',') + '\n' })
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = `内审报告_${new Date().toISOString().slice(0, 10)}.csv`; a.click()
    URL.revokeObjectURL(url)
    message.success('内审报告已导出')
  }

  const voucherColumns: ColumnsType<any> = [
    { title: '凭证号', dataIndex: 'voucher_no', width: 150 },
    { title: '日期', dataIndex: 'voucher_date', width: 100 },
    { title: '摘要', dataIndex: 'summary', ellipsis: true },
    { title: '借方合计', dataIndex: 'total_debit', width: 120, render: (v: number) => v ? `¥${v.toLocaleString()}` : '-' },
    { title: '贷方合计', dataIndex: 'total_credit', width: 120, render: (v: number) => v ? `¥${v.toLocaleString()}` : '-' },
    { title: '创建方式', dataIndex: 'created_by', width: 80, render: (v: string) => <Tag color={v === 'ai' ? 'purple' : 'default'}>{v === 'ai' ? 'AI' : '手工'}</Tag> },
    { title: '操作', width: 200, render: (_: any, r: any) => (
        <Space>
          <Button type="primary" size="small" icon={<CheckOutlined />} onClick={() => handleVoucherAudit(r)}>审计通过</Button>
          <Button size="small" danger icon={<CloseOutlined />} onClick={() => handleVoucherReject(r)}>驳回</Button>
        </Space>
      )},
  ]

  const filingColumns: ColumnsType<any> = [
    { title: '税种', dataIndex: 'tax_type', width: 120, render: (t: string) => {
        const m: Record<string, string> = { vat: '增值税', corporate_income: '企业所得税', individual_income: '个人所得税', stamp_duty: '印花税' }
        return <Tag color="blue">{m[t] || t}</Tag>
    }},
    { title: '所属期', dataIndex: 'period', width: 100 },
    { title: '状态', dataIndex: 'status', width: 90, render: (s: string) => <Tag color={s === 'pending_review' ? 'orange' : 'blue'}>{s === 'pending_review' ? '待审核' : '待处理'}</Tag> },
    { title: '操作', width: 200, render: (_: any, r: any) => (
        <Space>
          <Button type="primary" size="small" icon={<CheckOutlined />} onClick={() => handleFilingApprove(r)}>审核通过</Button>
          <Button size="small" danger icon={<CloseOutlined />} onClick={() => handleFilingReject(r)}>驳回</Button>
        </Space>
      )},
  ]

  const auditHistoryColumns: ColumnsType<any> = [
    { title: '时间', dataIndex: 'created_at', width: 170, render: (v: string) => v?.slice(0, 19) },
    { title: '对象', dataIndex: 'target_type', width: 80, render: (t: string) => {
        const m: Record<string, string> = { document: '凭证', voucher: '凭证', filing: '申报' }
        return <Tag>{m[t] || t}</Tag>
    }},
    { title: '操作', dataIndex: 'action', width: 90, render: (a: string) => {
        const m: Record<string, { color: string; text: string }> = {
          confirmed: { color: 'green', text: '已确认' }, approved: { color: 'green', text: '已通过' },
          rejected: { color: 'red', text: '已驳回' }, corrected: { color: 'orange', text: '已修正' },
        }
        const info = m[a] || { color: 'default', text: a }
        return <Tag color={info.color}>{info.text}</Tag>
    }},
    { title: '操作人', dataIndex: 'operator', width: 80 },
    { title: '详情', dataIndex: 'detail', ellipsis: true, render: (d: any) => typeof d === 'string' ? d : JSON.stringify(d || '') },
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 24 }}>
        <Typography.Title level={4} style={{ margin: 0 }}><AuditOutlined /> 内审工作台</Typography.Title>
        <Space>
          <Button icon={<ExportOutlined />} onClick={handleExportReport}>导出内审报告</Button>
          <Button icon={<HistoryOutlined />} onClick={fetchAll} loading={loading}>刷新</Button>
        </Space>
      </div>

      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}><Card hoverable><Statistic title="待审核凭证" value={summary.pending_vouchers || 0} valueStyle={{ color: '#1677ff' }} prefix={<AuditOutlined />} suffix="张" /></Card></Col>
        <Col span={6}><Card hoverable><Statistic title="待审核申报" value={summary.pending_filings || 0} valueStyle={{ color: '#fa8c16' }} prefix={<WarningOutlined />} suffix="项" /></Card></Col>
        <Col span={6}><Card hoverable><Statistic title="本月审计完成" value={summary.audited_this_month || 0} valueStyle={{ color: '#52c41a' }} prefix={<CheckCircleOutlined />} suffix="项" /></Card></Col>
        <Col span={6}><Card hoverable><Statistic title="发现问题" value={summary.issues_found || 0} valueStyle={{ color: '#ff4d4f' }} prefix={<CloseOutlined />} suffix="条" /></Card></Col>
      </Row>

      <Tabs defaultActiveKey="vouchers" items={[
        {
          key: 'vouchers',
          label: `凭证审计 (${pendingVouchers.length})`,
          children: (
            <Table dataSource={pendingVouchers} columns={voucherColumns} rowKey="id" pagination={false}
              size="small" loading={loading} locale={{ emptyText: '暂无待审核凭证' }} />
          ),
        },
        {
          key: 'filings',
          label: `申报审计 (${pendingFilings.length})`,
          children: (
            <Table dataSource={pendingFilings} columns={filingColumns} rowKey="id" pagination={false}
              size="small" loading={loading} locale={{ emptyText: '暂无待审核申报' }} />
          ),
        },
        {
          key: 'batch',
          label: <span><ThunderboltOutlined /> 批量审账</span>,
          children: <BatchAuditPanel />,
        },
        {
          key: 'history',
          label: '内审记录',
          children: (
            <Table dataSource={recentAudits} columns={auditHistoryColumns} rowKey="id" pagination={false}
              size="small" loading={loading} locale={{ emptyText: '暂无内审记录' }} />
          ),
        },
      ]} />

      <Modal title="内审评分" open={confirmOpen} onOk={handleVoucherConfirm} onCancel={() => setConfirmOpen(false)} okText="确认通过">
        <div style={{ marginBottom: 16 }}>
          <Text strong>凭证号：</Text><Text>{selectedVoucher?.voucher_no}</Text><br />
          <Text strong>摘要：</Text><Text>{selectedVoucher?.summary}</Text>
        </div>
        <div style={{ marginBottom: 16 }}>
          <Text strong>质量评分：</Text>
          <Rate value={auditScore} onChange={setAuditScore} />
          <Text type="secondary" style={{ marginLeft: 8 }}>
            {auditScore <= 2 ? '需改进' : auditScore === 3 ? '合格' : auditScore === 4 ? '良好' : '优秀'}
          </Text>
        </div>
        <div>
          <Text strong>内审意见：</Text>
          <Input.TextArea value={auditComment} onChange={e => setAuditComment(e.target.value)} placeholder="内审意见（可选）" rows={3} style={{ marginTop: 8 }} />
        </div>
      </Modal>
    </div>
  )
}

function BatchAuditPanel() {
  const [rules, setRules] = useState<any[]>([])
  const [selectedRules, setSelectedRules] = useState<string[]>([])
  const [period, setPeriod] = useState(dayjs().format('YYYY-MM'))
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<any>(null)
  const { message } = App.useApp()

  const fetchRules = async () => {
    try {
      const res: any = await auditApi.rules()
      setRules(res.rules || [])
      setSelectedRules((res.rules || []).map((r: any) => r.key))
    } catch { /* */ }
  }

  useEffect(() => { fetchRules() }, [])

  const handleRun = async () => {
    setRunning(true)
    try {
      const res: any = await auditApi.batchAudit({
        rules: selectedRules.length > 0 ? selectedRules : undefined,
        period,
      })
      setResult(res)
      if (res.blocker_clients > 0) {
        message.warning(`审账完成：${res.blocker_clients} 个客户有阻断问题`)
      } else {
        message.success(`审账完成：${res.passed_clients}/${res.total_clients} 通过`)
      }
    } catch { message.error('批量审账失败') }
    setRunning(false)
  }

  const gradeColor: Record<string, string> = { excellent: 'green', good: 'blue', warning: 'orange', danger: 'red' }
  const gradeText: Record<string, string> = { excellent: '优秀', good: '良好', warning: '关注', danger: '危险' }

  return (
    <div>
      <Card style={{ marginBottom: 16 }}>
        <Space wrap>
          <Select mode="multiple" placeholder="选择审计规则" value={selectedRules} onChange={setSelectedRules}
            style={{ minWidth: 280 }} maxTagCount={3}
            options={rules.map(r => ({ label: `${r.name} (${r.category})`, value: r.key }))} />
          <DatePicker picker="month" value={dayjs(period, 'YYYY-MM')} onChange={(d) => d && setPeriod(d.format('YYYY-MM'))} />
          <Button type="primary" icon={<ThunderboltOutlined />} loading={running} onClick={handleRun} danger>
            执行批量审账
          </Button>
        </Space>
        <div style={{ marginTop: 8 }}>
          <Text type="secondary">将对全部活跃客户执行 {selectedRules.length || rules.length} 项审计规则</Text>
        </div>
      </Card>

      {result && (
        <>
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={4}><Card><Statistic title="客户总数" value={result.total_clients} /></Card></Col>
            <Col span={4}><Card><Statistic title="通过" value={result.passed_clients} valueStyle={{ color: 'green' }} /></Card></Col>
            <Col span={4}><Card><Statistic title="未通过" value={result.failed_clients} valueStyle={{ color: 'red' }} /></Card></Col>
            <Col span={4}><Card><Statistic title="阻断问题" value={result.blocker_clients} valueStyle={{ color: '#dc2626' }} /></Card></Col>
            <Col span={4}><Card><Statistic title="总问题数" value={result.total_issues} /></Card></Col>
            <Col span={4}><Card><Statistic title="审计规则" value={result.rules_executed} /></Card></Col>
          </Row>

          {/* 规则统计 */}
          {result.rule_stats && (
            <Card title="规则命中统计" size="small" style={{ marginBottom: 16 }}>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12 }}>
                {Object.entries(result.rule_stats).map(([key, stat]: [string, any]) => (
                  <Tag key={key} color={stat.failed > 0 ? 'red' : 'green'}>
                    {stat.name}: {stat.passed}/{stat.total}
                  </Tag>
                ))}
              </div>
            </Card>
          )}

          {/* 各客户审计结果 */}
          {result.clients?.map((client: any) => (
            <Card key={client.client_id} size="small" title={
              <Space>
                <Progress type="circle" percent={Math.round(client.score / client.max_score * 100)} size={24}
                  strokeColor={gradeColor[client.grade]} />
                <span>{client.client_name}</span>
                <Tag color={gradeColor[client.grade]}>{gradeText[client.grade]}</Tag>
                <Text type="secondary">{client.voucher_count} 张凭证</Text>
              </Space>
            } style={{ marginBottom: 8 }}
            extra={
              <Space>
                <Tag color={client.blocker_count > 0 ? 'red' : 'default'}>{client.blocker_count} 阻断</Tag>
                <Tag color={client.warning_count > 0 ? 'orange' : 'default'}>{client.warning_count} 预警</Tag>
              </Space>
            }>
              {client.issues.length === 0 ? (
                <Text type="secondary">全部检查通过</Text>
              ) : (
                <Table dataSource={client.issues} rowKey="rule_key" size="small" pagination={false}
                  columns={[
                    { title: '规则', dataIndex: 'rule_name', width: 120 },
                    { title: '类别', dataIndex: 'category', width: 90 },
                    { title: '严重', dataIndex: 'severity', width: 70,
                      render: (s: string) => <Tag color={s === 'blocker' ? 'red' : s === 'warning' ? 'orange' : 'default'}>{s}</Tag> },
                    { title: '详情', dataIndex: 'detail', ellipsis: true },
                  ]} />
              )}
            </Card>
          ))}
        </>
      )}
    </div>
  )
}
