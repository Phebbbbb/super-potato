import { useState, useEffect } from 'react'
import { Card, Table, Tag, Button, Space, App, Row, Col, Statistic, Modal, Input, Form, Rate, Tabs, Typography } from 'antd'
import { CheckOutlined, CloseOutlined, EyeOutlined, AuditOutlined, WarningOutlined, CheckCircleOutlined, HistoryOutlined, ExportOutlined } from '@ant-design/icons'
import { auditApi, voucherApi, filingApi, feedbackApi } from '@/services/api'
import { useClient } from '@/contexts/ClientContext'
import type { ColumnsType } from 'antd/es/table'

const { Text, Title } = Typography

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

  // Voucher audit actions
  const handleVoucherAudit = (record: any) => {
    setSelectedVoucher(record)
    setAuditScore(3)
    setAuditComment('')
    setConfirmOpen(true)
  }

  const handleVoucherConfirm = async () => {
    try {
      await voucherApi.confirm(selectedVoucher.id, { reviewer: '内审员', comment: `[内审评分:${auditScore}/5] ${auditComment}` })
      message.success('凭证审核通过')
      setConfirmOpen(false)
      fetchAll()
    } catch (e: any) { message.error(e?.response?.data?.detail || '审核失败') }
  }

  const handleVoucherReject = async (record: any) => {
    Modal.confirm({
      title: '驳回凭证',
      icon: <WarningOutlined />,
      content: (
        <Input.TextArea id="audit-reject-reason" placeholder="请输入驳回原因" rows={3} />
      ),
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

  // Filing audit actions
  const handleFilingApprove = async (record: any) => {
    try {
      await feedbackApi.reviewFiling(record.id, { action: 'approve', comment: '内审通过，提交申报', reviewer: '内审员' })
      message.success('申报已审核通过')
      fetchAll()
    } catch (e: any) { message.error(e?.response?.data?.detail || '审核失败') }
  }

  const handleFilingReject = async (record: any) => {
    Modal.confirm({
      title: '驳回申报',
      content: (
        <Input.TextArea id="filing-reject-reason" placeholder="请输入驳回原因" rows={3} />
      ),
      onOk: async () => {
        const reason = (document.getElementById('filing-reject-reason') as HTMLTextAreaElement)?.value || '内审驳回'
        try {
          await feedbackApi.reviewFiling(record.id, { action: 'reject', comment: reason, reviewer: '内审员' })
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
    rows.forEach(r => {
      csv += Object.values(r).map(v => {
        const s = String(v).replace(/"/g, '""')
        return s.includes(',') ? `"${s}"` : s
      }).join(',') + '\n'
    })
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
    {
      title: '操作', width: 200,
      render: (_: any, r: any) => (
        <Space>
          <Button type="primary" size="small" icon={<CheckOutlined />} onClick={() => handleVoucherAudit(r)}>审计通过</Button>
          <Button size="small" danger icon={<CloseOutlined />} onClick={() => handleVoucherReject(r)}>驳回</Button>
        </Space>
      ),
    },
  ]

  const filingColumns: ColumnsType<any> = [
    { title: '税种', dataIndex: 'tax_type', width: 120, render: (t: string) => {
        const m: Record<string, string> = { vat: '增值税', corporate_income: '企业所得税', individual_income: '个人所得税', stamp_duty: '印花税' }
        return <Tag color="blue">{m[t] || t}</Tag>
    }},
    { title: '所属期', dataIndex: 'period', width: 100 },
    { title: '状态', dataIndex: 'status', width: 90,
      render: (s: string) => <Tag color={s === 'pending_review' ? 'orange' : 'blue'}>{s === 'pending_review' ? '待审核' : '待处理'}</Tag>,
    },
    {
      title: '操作', width: 200,
      render: (_: any, r: any) => (
        <Space>
          <Button type="primary" size="small" icon={<CheckOutlined />} onClick={() => handleFilingApprove(r)}>审核通过</Button>
          <Button size="small" danger icon={<CloseOutlined />} onClick={() => handleFilingReject(r)}>驳回</Button>
        </Space>
      ),
    },
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
        <h2><AuditOutlined /> 内审工作台</h2>
        <Space>
          <Button icon={<ExportOutlined />} onClick={handleExportReport}>导出内审报告</Button>
          <Button icon={<HistoryOutlined />} onClick={fetchAll} loading={loading}>刷新</Button>
        </Space>
      </div>

      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card hoverable><Statistic title="待审核凭证" value={summary.pending_vouchers || 0} valueStyle={{ color: '#1677ff' }} prefix={<AuditOutlined />} suffix="张" /></Card>
        </Col>
        <Col span={6}>
          <Card hoverable><Statistic title="待审核申报" value={summary.pending_filings || 0} valueStyle={{ color: '#fa8c16' }} prefix={<WarningOutlined />} suffix="项" /></Card>
        </Col>
        <Col span={6}>
          <Card hoverable><Statistic title="本月审计完成" value={summary.audited_this_month || 0} valueStyle={{ color: '#52c41a' }} prefix={<CheckCircleOutlined />} suffix="项" /></Card>
        </Col>
        <Col span={6}>
          <Card hoverable><Statistic title="发现问题" value={summary.issues_found || 0} valueStyle={{ color: '#ff4d4f' }} prefix={<CloseOutlined />} suffix="条" /></Card>
        </Col>
      </Row>

      <Card style={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
        <Tabs items={[
          {
            key: 'vouchers', label: `凭证审计队列 (${pendingVouchers.length})`,
            children: (
              <Table dataSource={pendingVouchers} columns={voucherColumns} rowKey="id" pagination={false}
                size="small" loading={loading} locale={{ emptyText: '暂无待审核凭证' }} />
            ),
          },
          {
            key: 'filings', label: `申报审计队列 (${pendingFilings.length})`,
            children: (
              <Table dataSource={pendingFilings} columns={filingColumns} rowKey="id" pagination={false}
                size="small" loading={loading} locale={{ emptyText: '暂无待审核申报' }} />
            ),
          },
          {
            key: 'history', label: '内审记录',
            children: (
              <Table dataSource={recentAudits} columns={auditHistoryColumns} rowKey="id" pagination={false}
                size="small" loading={loading} locale={{ emptyText: '暂无内审记录' }} />
            ),
          },
        ]} />
      </Card>

      {/* 内审评分弹窗 */}
      <Modal
        title="内审评分"
        open={confirmOpen}
        onOk={handleVoucherConfirm}
        onCancel={() => setConfirmOpen(false)}
        okText="确认通过"
      >
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
          <Input.TextArea value={auditComment} onChange={e => setAuditComment(e.target.value)}
            placeholder="内审意见（可选）" rows={3} style={{ marginTop: 8 }} />
        </div>
      </Modal>
    </div>
  )
}
