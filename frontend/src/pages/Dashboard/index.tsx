import { useEffect, useState } from 'react'
import { Row, Col, Card, Statistic, Table, Spin, Tag, Typography, Button, Tabs, App } from 'antd'
import {
  BookOutlined, DollarOutlined, AuditOutlined,
  RobotOutlined, QrcodeOutlined, FileTextOutlined,
  BankOutlined, EnvironmentOutlined, CustomerServiceOutlined,
  SafetyOutlined, InboxOutlined, ThunderboltOutlined,
} from '@ant-design/icons'
import { reportApi, voucherApi, documentApi, filingApi, rpaApi } from '@/services/api'
import { useClient } from '@/contexts/ClientContext'
import { useNavigate } from 'react-router-dom'
import dayjs from 'dayjs'

const { Title, Text } = Typography

export default function Dashboard() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [vouchers, setVouchers] = useState<any[]>([])
  const [documents, setDocuments] = useState<any[]>([])
  const [filings, setFilings] = useState<any[]>([])
  const [autoProcessing, setAutoProcessing] = useState(false)
  const [data, setData] = useState<any>({
    monthly_voucher_count: 0, monthly_income: 0, monthly_expense: 0, estimated_tax: 0, risk_count: 0,
  })
  const { currentClientId } = useClient()
  const navigate = useNavigate()
  const { message } = App.useApp()

  const fetchData = () => {
    setLoading(true)
    setError(null)
    const params = { page_size: 500, client_id: currentClientId || undefined }
    Promise.all([
      reportApi.dashboard(),
      voucherApi.list({ page: 1, page_size: 500, client_id: currentClientId || undefined }),
      documentApi.list({ ...params, page: 1 }),
      filingApi.list({ ...params, page: 1 }),
    ]).then(([dash, vRes, dRes, fRes]: any[]) => {
      if (dash) setData((prev: any) => ({ ...prev, ...dash }))
      setVouchers(vRes?.items || [])
      setDocuments(dRes?.items || [])
      setFilings(fRes?.items || [])
      setLoading(false)
    }).catch((err) => {
      setError(err?.detail || '加载数据失败')
      setLoading(false)
    })
  }

  useEffect(() => { fetchData() }, [currentClientId])

  const handleAutoProcess = async () => {
    if (!currentClientId) return
    setAutoProcessing(true)
    try {
      const res: any = await rpaApi.autoProcess(currentClientId)
      message.success(res?.summary || '自动加工完成')
      fetchData()
    } catch (err: any) {
      message.error(err?.detail || '自动加工失败')
    }
    setAutoProcessing(false)
  }

  const statCards = [
    { title: '本期待申报税种', value: filings.filter((f: any) => f.status === 'pending').length, suffix: '项', period: `${dayjs().format('YYYY年M月')}`, color: '#2563eb', link: '/tax-filings' },
    { title: '票据总数', value: data.monthly_voucher_count || documents.length, suffix: '张', period: `${dayjs().format('YYYY年M月')}`, color: '#2563eb', link: '/documents' },
    { title: '涉税风险提示', value: data.risk_count || 0, suffix: '条', period: '自查参考，以税务机关核定为准', color: (data.risk_count || 0) > 0 ? '#b91c1c' : '#2d6a4f', link: '/tax-risk' },
    { title: '已归档档案', value: vouchers.filter((v: any) => v.status === 'confirmed').length, suffix: '份', period: `截至${dayjs().format('YYYY年M月')}`, color: '#2563eb', link: '/reports' },
  ]

  const pendingFilingCount = filings.filter((f: any) => f.status === 'pending').length

  const quickLinks = [
    { title: '一键申报', desc: '自动汇总凭证数据，生成申报表', icon: <AuditOutlined />, link: '/tax-filings' },
    { title: '票据导入', desc: '上传发票/回单，OCR 自动识别', icon: <FileTextOutlined />, link: '/documents' },
    { title: '报表导出', desc: '三大财务报表一键导出 CSV', icon: <BookOutlined />, link: '/reports' },
    { title: '风险自检', desc: '税负率/进销项/零申报异常检测', icon: <SafetyOutlined />, link: '/tax-risk' },
  ]

  const bizEntries = [
    { title: '账务凭证', icon: <BookOutlined />, desc: 'AI 智能生成 + 手工录入', link: '/vouchers' },
    { title: '薪酬台账', icon: <DollarOutlined />, desc: '工资计算 · 个税代扣', link: '/payroll' },
    { title: '银企对账', icon: <BankOutlined />, desc: '流水导入 · 自动匹配', link: '/bank-reconciliation' },
    { title: '票据追溯', icon: <QrcodeOutlined />, desc: 'QR 全链路溯源查询', link: '/trace' },
    { title: '外勤任务', icon: <EnvironmentOutlined />, desc: '任务分派 · 现场留痕', link: '/field-tasks' },
    { title: '法规查询', icon: <CustomerServiceOutlined />, desc: '财税政策智能问答', link: '/ai-agent' },
    { title: 'RPA 自动化', icon: <RobotOutlined />, desc: '自动扫描 · 一键加工', link: '/rpa-tasks' },
    { title: '系统设置', icon: <AuditOutlined />, desc: '科目 · 用户 · 配置', link: '/settings' },
  ]

  const voucherColumns = [
    { title: '凭证号', dataIndex: 'voucher_no', width: 150 },
    { title: '日期', dataIndex: 'voucher_date', width: 110 },
    { title: '摘要', dataIndex: 'summary', ellipsis: true },
    { title: '借方合计', dataIndex: 'total_debit', width: 130, align: 'right' as const, render: (v: number) => v ? `¥${v.toLocaleString()}` : '-' },
    { title: '贷方合计', dataIndex: 'total_credit', width: 130, align: 'right' as const, render: (v: number) => v ? `¥${v.toLocaleString()}` : '-' },
    {
      title: '状态', dataIndex: 'status', width: 90,
      render: (s: string) => {
        const map: Record<string, { color: string; text: string }> = {
          draft: { color: 'default', text: '草稿' }, confirmed: { color: 'green', text: '已确认' }, rejected: { color: 'red', text: '已驳回' },
        }
        const m = map[s] || { color: 'default', text: s }
        return <Tag color={m.color}>{m.text}</Tag>
      },
    },
  ]

  const docColumns = [
    { title: '文件名', dataIndex: 'file_name', ellipsis: true },
    { title: '类型', dataIndex: 'doc_type', width: 90, render: (t: string) => {
        const m: Record<string, string> = { invoice: '发票', receipt: '回单', contract: '合同', bank_statement: '银行流水', other: '其他' }
        return <Tag>{m[t] || t}</Tag>
    }},
    { title: 'OCR状态', dataIndex: 'ocr_status', width: 90, render: (s: string) => <Tag color={s === 'done' ? 'green' : 'orange'}>{s === 'done' ? '已识别' : '待处理'}</Tag> },
    { title: '上传时间', dataIndex: 'created_at', width: 170, render: (v: string) => v?.slice(0, 19) },
  ]

  const filingColumns = [
    { title: '税种', dataIndex: 'tax_type', width: 110, render: (t: string) => {
        const m: Record<string, string> = { vat: '增值税', corporate_income: '企业所得税', individual_income: '个人所得税', stamp_duty: '印花税', surtax: '附加税' }
        return <Tag color="blue">{m[t] || t}</Tag>
    }},
    { title: '所属期', dataIndex: 'period', width: 100 },
    { title: '状态', dataIndex: 'status', width: 90,
      render: (s: string) => {
        const m: Record<string, { color: string; text: string }> = {
          pending: { color: 'orange', text: '待申报' }, submitted: { color: 'blue', text: '已提交' },
          success: { color: 'green', text: '申报成功' }, failed: { color: 'red', text: '失败' },
        }
        const info = m[s] || { color: 'default', text: s }
        return <Tag color={info.color}>{info.text}</Tag>
      },
    },
    { title: '提交时间', dataIndex: 'submitted_at', width: 170, render: (v: string) => v?.slice(0, 19) || '-' },
  ]

  const tabItems = [
    {
      key: 'vouchers',
      label: `记账凭证 (${vouchers.length})`,
      children: (
        <Table dataSource={vouchers} columns={voucherColumns} rowKey="id" size="small" pagination={false}
          scroll={{ y: 360 }}
          locale={{ emptyText: <div style={{ padding: 40 }}><InboxOutlined style={{ fontSize: 40, color: '#d9d9d9' }} /><div style={{ marginTop: 8, color: '#94a3b8' }}>暂无凭证数据，请先上传票据</div></div> }} />
      ),
    },
    {
      key: 'documents',
      label: `原始凭证 (${documents.length})`,
      children: (
        <Table dataSource={documents} columns={docColumns} rowKey="id" size="small" pagination={false}
          scroll={{ y: 360 }}
          locale={{ emptyText: <div style={{ padding: 40 }}><InboxOutlined style={{ fontSize: 40, color: '#d9d9d9' }} /><div style={{ marginTop: 8, color: '#94a3b8' }}>暂无票据，请先上传</div></div> }} />
      ),
    },
    {
      key: 'filings',
      label: `纳税申报 (${filings.length})`,
      children: (
        <Table dataSource={filings} columns={filingColumns} rowKey="id" size="small" pagination={false}
          scroll={{ y: 360 }}
          locale={{ emptyText: <div style={{ padding: 40 }}><InboxOutlined style={{ fontSize: 40, color: '#d9d9d9' }} /><div style={{ marginTop: 8, color: '#94a3b8' }}>暂无申报记录</div></div> }} />
      ),
    },
  ]

  return (
    <Spin spinning={loading}>
      {/* 标题行 */}
      <div style={{ marginBottom: 16 }}>
        <Title level={5} style={{ margin: 0, color: '#1e293b' }}>工作台</Title>
        <Text type="secondary" style={{ fontSize: 12 }}>
          数据更新：{dayjs().format('YYYY-MM-DD HH:mm')} &nbsp;·&nbsp; 当前企业主体已实名认证
        </Text>
      </div>

      {/* 数据总览卡片 */}
      <Row gutter={[16, 16]}>
        {statCards.map(card => (
          <Col xs={24} sm={12} md={6} key={card.title}>
            <div className="stat-card" onClick={() => navigate(card.link)} style={{ padding: '12px 16px', cursor: 'pointer' }}>
              <Text type="secondary" style={{ fontSize: 12 }}>{card.title}</Text>
              <div style={{ fontSize: 28, fontWeight: 700, color: card.color, margin: '4px 0', lineHeight: 1.2 }}>
                {typeof card.value === 'number' ? card.value.toLocaleString() : card.value}
                <span style={{ fontSize: 14, fontWeight: 400, color: '#94a3b8' }}> {card.suffix}</span>
              </div>
              <Text type="secondary" style={{ fontSize: 11 }}>{card.period}</Text>
            </div>
          </Col>
        ))}
      </Row>

      {/* 自动化管道 — 核心竞争优势 */}
      <div className="biz-card" style={{ marginTop: 12, padding: '12px 16px', background: 'linear-gradient(135deg, #eff6ff 0%, #f0fdf4 100%)', border: '1px solid #dbeafe', borderRadius: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <ThunderboltOutlined style={{ fontSize: 22, color: '#2563eb' }} />
            <div>
              <Text strong style={{ fontSize: 14 }}>全自动财税管道</Text>
              <br />
              <Text type="secondary" style={{ fontSize: 11 }}>
                票据 OCR → AI 记账 → 自动申报 → Playwright 提交电子税务局
                &nbsp;·&nbsp; 零 RPA 授权费，年省 ¥3,000-8,000
              </Text>
            </div>
          </div>
          <Button
            type="primary"
            size="middle"
            icon={<ThunderboltOutlined />}
            loading={autoProcessing}
            onClick={handleAutoProcess}
            disabled={!currentClientId}
          >
            一键自动加工
          </Button>
        </div>
        {error && (
          <div style={{ marginTop: 8, padding: '6px 12px', background: '#fef2f2', borderRadius: 4, border: '1px solid #fecaca' }}>
            <Text type="danger" style={{ fontSize: 12 }}>{error}</Text>
            <Button type="link" size="small" onClick={fetchData} style={{ marginLeft: 8 }}>重试</Button>
          </div>
        )}
      </div>

      {/* 高频业务 */}
      <Row gutter={[12, 12]} style={{ marginTop: 12 }}>
        {quickLinks.map(link => (
          <Col xs={24} sm={12} md={6} key={link.title}>
            <div className="quick-card" onClick={() => navigate(link.link)} style={{ padding: '10px 14px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
                <span style={{ fontSize: 16, color: '#2563eb' }}>{link.icon}</span>
                <Text strong style={{ fontSize: 14 }}>{link.title}</Text>
              </div>
              <Text type="secondary" style={{ fontSize: 12 }}>{link.desc}</Text>
            </div>
          </Col>
        ))}
      </Row>

      {/* 更多模块 */}
      <div style={{ marginTop: 12 }}>
        <Text type="secondary" style={{ fontSize: 12 }}>更多业务模块</Text>
        <Row gutter={[8, 8]} style={{ marginTop: 6 }}>
          {bizEntries.map(entry => (
            <Col xs={12} sm={8} md={6} lg={4} xl={3} key={entry.title}>
              <div className="quick-card" onClick={() => navigate(entry.link)}
                style={{ padding: '12px 8px', textAlign: 'center' }}>
                <div style={{ fontSize: 20, color: '#2563eb', marginBottom: 4 }}>{entry.icon}</div>
                <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 2 }}>{entry.title}</div>
                <Text type="secondary" style={{ fontSize: 11 }}>{entry.desc}</Text>
              </div>
            </Col>
          ))}
        </Row>
      </div>

      {/* 数据表格 — 凭证 / 票据 / 申报 合并到一个 Tab 组件中 */}
      <div style={{ marginTop: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
          <Text strong style={{ fontSize: 13 }}>财税数据总览</Text>
          <div style={{ display: 'flex', gap: 8 }}>
            <Button size="small" onClick={() => navigate('/vouchers')}>凭证管理 →</Button>
            <Button size="small" onClick={() => navigate('/documents')}>票据管理 →</Button>
            <Button size="small" onClick={() => navigate('/tax-filings')}>申报管理 →</Button>
          </div>
        </div>
        <Tabs items={tabItems} />
      </div>

      {/* 政策公告 */}
      <Row gutter={[16, 16]} style={{ marginTop: 12 }}>
        <Col span={24}>
          <div className="biz-card" style={{ padding: '12px 16px' }}>
            <Text strong style={{ fontSize: 13 }}>政策法规公告</Text>
            <div style={{ marginTop: 8, display: 'flex', gap: 24, flexWrap: 'wrap' }}>
              {[
                { title: '关于2026年增值税申报期限的通知', date: '2026-05-30', source: '国家税务总局' },
                { title: '关于延续实施企业所得税优惠政策的公告', date: '2026-05-15', source: '财政部 税务总局' },
                { title: '电子发票全流程管理规范（试行）', date: '2026-04-20', source: '国家税务总局' },
              ].map((item, i) => (
                <div key={i} style={{ cursor: 'pointer', flex: '1 1 280px', minWidth: 200 }}
                  onClick={() => navigate('/ai-agent')}>
                  <div style={{ fontSize: 13, color: '#334155', marginBottom: 2 }}>{item.title}</div>
                  <Text type="secondary" style={{ fontSize: 11 }}>{item.date} · {item.source}</Text>
                </div>
              ))}
            </div>
          </div>
        </Col>
      </Row>
    </Spin>
  )
}
