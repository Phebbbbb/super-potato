import { useEffect, useState } from 'react'
import { Row, Col, Card, Statistic, Table, Spin, Tag, Typography, Button, Tabs, App, Progress, Tooltip, Space, Modal } from 'antd'
import {
  RiseOutlined, FallOutlined, DollarOutlined, PercentageOutlined,
  BankOutlined, FileTextOutlined, AuditOutlined, WarningOutlined,
  CheckCircleOutlined, InboxOutlined, ArrowUpOutlined, ArrowDownOutlined,
  ThunderboltOutlined, SyncOutlined, SendOutlined,
} from '@ant-design/icons'
import { reportApi, voucherApi, documentApi, filingApi, announcementApi, batchApi, rpaApi } from '@/services/api'
import { useClient } from '@/contexts/ClientContext'
import { useNavigate } from 'react-router-dom'
import dayjs from 'dayjs'

const { Title, Text } = Typography

function TrendBar({ data, maxVal, label }: { data: { month: string; value: number }[]; maxVal: number; label: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'flex-end', gap: 4, height: 100, paddingTop: 8 }}>
      {data.map((d, i) => {
        const h = maxVal > 0 ? Math.max(4, (d.value / maxVal) * 88) : 4
        return (
          <Tooltip key={i} title={`${d.month}: ¥${d.value.toLocaleString()}`}>
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'flex-end', height: '100%' }}>
              <div style={{
                width: '100%', maxWidth: 32, height: h,
                background: i === data.length - 1 ? '#2563eb' : '#93c5fd',
                borderRadius: '4px 4px 0 0', transition: 'height 0.3s',
                minWidth: 12,
              }} />
              <Text style={{ fontSize: 10, color: '#94a3b8', marginTop: 4, transform: 'rotate(-30deg)', transformOrigin: 'top left', whiteSpace: 'nowrap' }}>
                {d.month.slice(5)}
              </Text>
            </div>
          </Tooltip>
        )
      })}
    </div>
  )
}

export default function Dashboard() {
  const [loading, setLoading] = useState(true)
  const [dash, setDash] = useState<any>(null)
  const [vouchers, setVouchers] = useState<any[]>([])
  const [documents, setDocuments] = useState<any[]>([])
  const [filings, setFilings] = useState<any[]>([])
  const [announcements, setAnnouncements] = useState<any[]>([])
  const { currentClientId } = useClient()
  const navigate = useNavigate()
  const { message } = App.useApp()

  const fetchData = () => {
    setLoading(true)
    const params = { page_size: 20, client_id: currentClientId || undefined }
    Promise.all([
      reportApi.dashboard(),
      voucherApi.list({ page: 1, page_size: 20, client_id: currentClientId || undefined }),
      documentApi.list({ ...params, page: 1 }),
      filingApi.list({ ...params, page: 1 }),
      announcementApi.list(5),
    ]).then(([dashRes, vRes, dRes, fRes, aRes]: any[]) => {
      setDash(dashRes)
      setVouchers(vRes?.items || [])
      setDocuments(dRes?.items || [])
      setFilings(fRes?.items || [])
      setAnnouncements(aRes?.items || [])
      setLoading(false)
    }).catch(() => setLoading(false))
  }

  // ===== 批量自动化操作状态 =====
  const [batchRunning, setBatchRunning] = useState(false)
  const [batchType, setBatchType] = useState('')
  const [batchResult, setBatchResult] = useState<any>(null)
  const [batchModalOpen, setBatchModalOpen] = useState(false)
  const [autoRate, setAutoRate] = useState<any>(null)

  const fetchAutoRate = async () => {
    try {
      const res: any = await reportApi.automationRate()
      setAutoRate(res)
    } catch { /* ignore */ }
  }

  const [periodClosing, setPeriodClosing] = useState(false)

  const handlePeriodClose = () => {
    Modal.confirm({
      title: '一键关账',
      content: '将执行：折旧计提 → 收入结转 → 费用结转 → 所得税预估 → 申报创建。确认继续？',
      onOk: async () => {
        setPeriodClosing(true)
        try {
          const res: any = await rpaApi.periodClose(currentClientId!)
          const s = res.summary
          message.success(`关账完成：收入 ¥${s.total_revenue?.toLocaleString()} | 费用 ¥${s.total_expense?.toLocaleString()} | 创建 ${s.filings_created} 项申报`)
          fetchData()
        } catch (e: any) { message.error(e?.detail || '关账失败') }
        setPeriodClosing(false)
      },
    })
  }

  const handleBatchAll = async (operation: string) => {
    setBatchRunning(true)
    setBatchType(operation === 'filing' ? '批量申报' : operation === 'invoice' ? '批量开票' : '全流程自动化')
    setBatchModalOpen(true)
    setBatchResult(null)
    try {
      const res: any = await batchApi.batchAllClients(operation)
      setBatchResult(res)
      if (res.results?.filing?.success > 0 || res.results?.invoice?.success > 0) {
        message.success(`批量操作完成：申报 ${res.results?.filing?.success || 0} 项，开票 ${res.results?.invoice?.success || 0} 项`)
      } else {
        message.info('当前无待处理任务')
      }
      fetchData()
    } catch (e: any) {
      message.error(e?.detail || '批量操作失败')
    }
    setBatchRunning(false)
  }

  useEffect(() => { fetchData(); fetchAutoRate() }, [currentClientId])

  if (loading || !dash) {
    return <Spin spinning><div style={{ height: 400 }} /></Spin>
  }

  const cm = dash.current_month || {}
  const bal = dash.balance || {}
  const ops = dash.operations || {}
  const revenueTrend = dash.trends?.revenue || []
  const taxTrend = dash.trends?.tax_burden || []
  const maxRevenue = Math.max(...revenueTrend.map((r: any) => r.revenue), 1)
  const maxTax = Math.max(...taxTrend.map((r: any) => r.tax_burden), 1)
  const pendingFilingCount = ops.pending_filings || 0
  const docProcessRate = ops.total_documents > 0 ? Math.round((ops.documents_processed / ops.total_documents) * 100) : 0

  return (
    <div>
      {/* ===== 标题行 ===== */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div>
          <Title level={5} style={{ margin: 0 }}>经营驾驶舱</Title>
          <Text type="secondary" style={{ fontSize: 12 }}>
            对标亿企赢 · 数据更新 {dayjs().format('HH:mm')} · 当前企业主体已实名认证
          </Text>
        </div>
        <Button size="small" onClick={fetchData}>刷新数据</Button>
      </div>

      {/* ===== KPI 核心指标卡片 ===== */}
      <Row gutter={[12, 12]}>
        <Col xs={12} sm={8} md={4}>
          <Card size="small" hoverable onClick={() => navigate('/reports')}>
            <Statistic
              title={<Text style={{ fontSize: 12 }}>本月收入</Text>}
              value={cm.revenue}
              precision={0}
              prefix={<RiseOutlined />}
              suffix="元"
              valueStyle={{ color: '#16a34a', fontSize: 22, fontWeight: 700 }}
            />
            <Text type="secondary" style={{ fontSize: 11 }}>主营业务 + 其他业务</Text>
          </Card>
        </Col>
        <Col xs={12} sm={8} md={4}>
          <Card size="small" hoverable onClick={() => navigate('/reports')}>
            <Statistic
              title={<Text style={{ fontSize: 12 }}>毛利</Text>}
              value={cm.gross_profit}
              precision={0}
              prefix={cm.gross_profit >= 0 ? <ArrowUpOutlined /> : <ArrowDownOutlined />}
              suffix="元"
              valueStyle={{ color: cm.gross_profit >= 0 ? '#16a34a' : '#dc2626', fontSize: 22, fontWeight: 700 }}
            />
            <Text type="secondary" style={{ fontSize: 11 }}>利润率 {cm.profit_margin}%</Text>
          </Card>
        </Col>
        <Col xs={12} sm={8} md={4}>
          <Card size="small" hoverable onClick={() => navigate('/tax-filings')}>
            <Statistic
              title={<Text style={{ fontSize: 12 }}>应缴增值税</Text>}
              value={cm.vat_payable}
              precision={0}
              prefix={<DollarOutlined />}
              suffix="元"
              valueStyle={{ color: cm.vat_payable > 0 ? '#d97706' : '#64748b', fontSize: 22, fontWeight: 700 }}
            />
            <Text type="secondary" style={{ fontSize: 11 }}>销项 {cm.output_vat?.toLocaleString()} - 进项 {cm.input_vat?.toLocaleString()}</Text>
          </Card>
        </Col>
        <Col xs={12} sm={8} md={4}>
          <Card size="small" hoverable onClick={() => navigate('/tax-filings')}>
            <Statistic
              title={<Text style={{ fontSize: 12 }}>预缴所得税</Text>}
              value={cm.est_cit}
              precision={0}
              prefix={<PercentageOutlined />}
              suffix="元"
              valueStyle={{ color: '#2563eb', fontSize: 22, fontWeight: 700 }}
            />
            <Text type="secondary" style={{ fontSize: 11 }}>按利润 2.5% 估算（小微企业）</Text>
          </Card>
        </Col>
        <Col xs={12} sm={8} md={4}>
          <Card size="small">
            <Statistic
              title="资金余额"
              value={bal.cash_bank}
              precision={0}
              prefix={<BankOutlined />}
              suffix="元"
              valueStyle={{ color: '#2563eb', fontSize: 22, fontWeight: 700 }}
            />
            <Text type="secondary" style={{ fontSize: 11 }}>应收 {bal.accounts_receivable?.toLocaleString()} | 应付 {bal.accounts_payable?.toLocaleString()}</Text>
          </Card>
        </Col>
        <Col xs={12} sm={8} md={4}>
          <Card size="small" hoverable onClick={() => navigate('/tax-risk')}>
            <Statistic
              title="票据处理率"
              value={docProcessRate}
              suffix="%"
              valueStyle={{ color: docProcessRate >= 80 ? '#16a34a' : '#d97706', fontSize: 22, fontWeight: 700 }}
            />
            <Progress percent={docProcessRate} size="small" showInfo={false} strokeColor={docProcessRate >= 80 ? '#16a34a' : '#d97706'} />
          </Card>
        </Col>
      </Row>

      {/* ===== 月度趋势 + 申报状态 ===== */}
      <Row gutter={[12, 12]} style={{ marginTop: 12 }}>
        <Col xs={24} md={14}>
          <Card size="small" title={<Text strong style={{ fontSize: 13 }}>月度收入趋势（近6个月）</Text>}
            extra={<Text type="secondary" style={{ fontSize: 11 }}>单位：元</Text>}>
            <TrendBar data={revenueTrend.map((r: any) => ({ month: r.month, value: r.revenue }))} maxVal={maxRevenue} label="收入" />
            <div style={{ marginTop: 4, display: 'flex', justifyContent: 'space-between' }}>
              {revenueTrend.map((r: any, i: number) => (
                <Text key={i} style={{ fontSize: 11, color: '#64748b' }}>
                  ¥{r.revenue > 10000 ? `${(r.revenue / 10000).toFixed(1)}万` : r.revenue.toLocaleString()}
                </Text>
              ))}
            </div>
          </Card>
        </Col>
        <Col xs={24} md={10}>
          <Card size="small" title={<Text strong style={{ fontSize: 13 }}>税负率趋势</Text>}
            extra={<Text type="secondary" style={{ fontSize: 11 }}>增值税/收入 %</Text>}>
            <TrendBar data={taxTrend.map((r: any) => ({ month: r.month, value: r.tax_burden }))} maxVal={maxTax} label="税负率" />
            <div style={{ marginTop: 4, display: 'flex', justifyContent: 'space-between' }}>
              {taxTrend.map((r: any, i: number) => (
                <Text key={i} style={{ fontSize: 11, color: r.tax_burden > 5 ? '#dc2626' : '#64748b' }}>
                  {r.tax_burden}%
                </Text>
              ))}
            </div>
          </Card>
        </Col>
      </Row>

      {/* ===== 运营指标 + 快捷入口 ===== */}
      <Row gutter={[12, 12]} style={{ marginTop: 12 }}>
        <Col xs={24} md={8}>
          <Card size="small" title={<Text strong style={{ fontSize: 13 }}>运营效率</Text>}>
            <Row gutter={[8, 12]}>
              <Col span={12}>
                <Statistic title="本月凭证" value={ops.vouchers_this_month} suffix="张" valueStyle={{ fontSize: 20 }} />
              </Col>
              <Col span={12}>
                <Statistic title="累计凭证" value={ops.total_vouchers} suffix="张" valueStyle={{ fontSize: 20 }} />
              </Col>
              <Col span={12}>
                <Statistic title="待申报" value={ops.pending_filings} suffix="项"
                  valueStyle={{ fontSize: 20, color: ops.pending_filings > 0 ? '#dc2626' : '#16a34a' }} />
              </Col>
              <Col span={12}>
                <Statistic title="已申报" value={ops.submitted_filings} suffix="项" valueStyle={{ fontSize: 20, color: '#16a34a' }} />
              </Col>
            </Row>
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card size="small" title={<Text strong style={{ fontSize: 13 }}>快捷操作</Text>}>
            <Space direction="vertical" style={{ width: '100%' }} size={8}>
              <Button block icon={<FileTextOutlined />} onClick={() => navigate('/documents')}>票据采集录入</Button>
              <Button block icon={<AuditOutlined />} onClick={() => navigate('/vouchers')}>AI 智能记账</Button>
              <Button block icon={<CheckCircleOutlined />} style={{ color: pendingFilingCount > 0 ? '#dc2626' : '#16a34a', borderColor: pendingFilingCount > 0 ? '#dc2626' : '#16a34a' }}
                onClick={() => navigate('/tax-filings')}>
                {pendingFilingCount > 0 ? `待申报 ${pendingFilingCount} 项 →` : '申报任务 →'}
              </Button>
              <Button block icon={<WarningOutlined />} onClick={() => navigate('/tax-risk')}>税务风险自查</Button>
            </Space>
          </Card>
        </Col>
      </Row>

      {/* ===== 全自动批量引擎（差异化核心）===== */}
      <Row gutter={[12, 12]} style={{ marginTop: 12 }}>
        <Col span={24}>
          <Card
            size="small"
            title={<Space><ThunderboltOutlined style={{ color: '#7c3aed' }} /><Text strong style={{ fontSize: 13 }}>全自动批量引擎 — 并行多客户自动化</Text></Space>}
            extra={<Tag color="purple" icon={<SyncOutlined spin={batchRunning} />}>{batchRunning ? '执行中...' : '零成本 RPA'}</Tag>}
          >
            {autoRate && (
              <Row gutter={[12, 8]} style={{ marginBottom: 12 }}>
                <Col xs={12} sm={6}>
                  <Statistic
                    title={<Text style={{ fontSize: 11 }}>综合自动化率</Text>}
                    value={autoRate.overall_automation_pct}
                    suffix="%"
                    valueStyle={{ fontSize: 18, color: autoRate.overall_automation_pct >= 80 ? '#16a34a' : '#d97706', fontWeight: 700 }}
                  />
                  <Progress percent={autoRate.overall_automation_pct} size="small" showInfo={false}
                    strokeColor={autoRate.overall_automation_pct >= 80 ? '#16a34a' : '#d97706'} />
                </Col>
                <Col xs={12} sm={6}>
                  <Statistic title={<Text style={{ fontSize: 11 }}>全自动客户</Text>} value={autoRate.fully_auto_clients} suffix={`/ ${autoRate.total_clients} 户`}
                    valueStyle={{ fontSize: 18, fontWeight: 700 }} />
                </Col>
                <Col xs={12} sm={6}>
                  <Statistic title={<Text style={{ fontSize: 11 }}>票据自动处理</Text>} value={autoRate.breakdown?.documents?.pct || 0} suffix="%"
                    valueStyle={{ fontSize: 16, color: '#2563eb' }} />
                </Col>
                <Col xs={12} sm={6}>
                  <Statistic title={<Text style={{ fontSize: 11 }}>凭证自动生成</Text>} value={autoRate.breakdown?.vouchers?.pct || 0} suffix="%"
                    valueStyle={{ fontSize: 16, color: '#7c3aed' }} />
                </Col>
              </Row>
            )}
            <Row gutter={[12, 12]}>
              <Col xs={24} sm={8}>
                <Card size="small" style={{ background: '#faf5ff', borderColor: '#e9d5ff' }}>
                  <Statistic
                    title={<Text style={{ fontSize: 12 }}>一键全客户申报</Text>}
                    value={batchRunning && batchType === '批量申报' ? '执行中...' : '并行提交'}
                    valueStyle={{ fontSize: 16, color: '#7c3aed' }}
                    prefix={<SendOutlined />}
                  />
                  <Button
                    block type="primary"
                    icon={<ThunderboltOutlined />}
                    loading={batchRunning && batchType === '批量申报'}
                    onClick={() => handleBatchAll('filing')}
                    style={{ marginTop: 8, background: '#7c3aed', borderColor: '#7c3aed' }}
                  >
                    一键全客户批量申报
                  </Button>
                  <Text type="secondary" style={{ fontSize: 10, display: 'block', marginTop: 4 }}>
                    扫描所有客户待申报项，并⾏提交电子税务局（最多 {3} 窗口并⾏）
                  </Text>
                </Card>
              </Col>
              <Col xs={24} sm={8}>
                <Card size="small" style={{ background: '#fef3c7', borderColor: '#fde68a' }}>
                  <Statistic
                    title={<Text style={{ fontSize: 12 }}>一键全客户开票</Text>}
                    value={batchRunning && batchType === '批量开票' ? '执行中...' : '并行开具'}
                    valueStyle={{ fontSize: 16, color: '#d97706' }}
                    prefix={<FileTextOutlined />}
                  />
                  <Button
                    block
                    icon={<ThunderboltOutlined />}
                    loading={batchRunning && batchType === '批量开票'}
                    onClick={() => handleBatchAll('invoice')}
                    style={{ marginTop: 8, borderColor: '#d97706', color: '#d97706' }}
                  >
                    一键全客户批量开票
                  </Button>
                  <Text type="secondary" style={{ fontSize: 10, display: 'block', marginTop: 4 }}>
                    扫描所有客户草稿发票，并行登录电子税务局开具数电票
                  </Text>
                </Card>
              </Col>
              <Col xs={24} sm={8}>
                <Card size="small" style={{ background: '#f0fdf4', borderColor: '#bbf7d0' }}>
                  <Statistic
                    title={<Text style={{ fontSize: 12 }}>全流程自动化</Text>}
                    value={batchRunning && batchType === '全流程自动化' ? '执行中...' : '申报 + 开票'}
                    valueStyle={{ fontSize: 16, color: '#16a34a' }}
                    prefix={<SyncOutlined />}
                  />
                  <Button
                    block
                    icon={<ThunderboltOutlined />}
                    loading={batchRunning && batchType === '全流程自动化'}
                    onClick={() => handleBatchAll('both')}
                    style={{ marginTop: 8, borderColor: '#16a34a', color: '#16a34a' }}
                  >
                    一键申报+开票全流程
                  </Button>
                  <Text type="secondary" style={{ fontSize: 10, display: 'block', marginTop: 4 }}>
                    先批量申报再批量开票，全流程无人值守（适用于征期集中处理）
                  </Text>
                </Card>
              </Col>
            </Row>
            <Row gutter={[12, 12]} style={{ marginTop: 4 }}>
              <Col span={24}>
                <Card size="small" style={{ background: '#fff7ed', borderColor: '#fed7aa' }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <div>
                      <Text strong style={{ fontSize: 13 }}>一键期末关账</Text>
                      <Text type="secondary" style={{ fontSize: 11, marginLeft: 8 }}>
                        折旧计提 → 收入结转 → 费用结转 → 所得税预估 → 申报创建 — 原来2-3小时 → 1次点击
                      </Text>
                    </div>
                    <Button
                      type="primary"
                      icon={<ThunderboltOutlined />}
                      loading={periodClosing}
                      onClick={handlePeriodClose}
                      style={{ background: '#ea580c', borderColor: '#ea580c' }}
                    >
                      一键关账
                    </Button>
                  </div>
                </Card>
              </Col>
            </Row>
          </Card>
        </Col>
      </Row>

      {/* ===== 批量操作结果弹窗 ===== */}
      <Modal
        title={`批量操作结果 — ${batchType}`}
        open={batchModalOpen}
        onCancel={() => setBatchModalOpen(false)}
        footer={<Button onClick={() => setBatchModalOpen(false)}>关闭</Button>}
        width={600}
      >
        {batchRunning ? (
          <div style={{ textAlign: 'center', padding: 40 }}>
            <Spin size="large" />
            <div style={{ marginTop: 16, fontSize: 14, color: '#64748b' }}>正在并行处理多客户任务…</div>
            <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 4 }}>最多同时处理 {3} 个客户，请耐心等待</div>
          </div>
        ) : batchResult ? (
          <div>
            <Row gutter={16}>
              <Col span={12}>
                <Statistic title="客户总数" value={batchResult.clients_count} suffix="户" />
              </Col>
              {batchResult.results?.filing && (
                <Col span={12}>
                  <Card size="small" style={{ background: '#faf5ff' }}>
                    <Statistic
                      title="批量申报"
                      value={batchResult.results.filing.success || 0}
                      suffix={`/ ${batchResult.results.filing.total || 0}`}
                      valueStyle={{ color: (batchResult.results.filing.failed || 0) > 0 ? '#d97706' : '#16a34a' }}
                    />
                    {(batchResult.results.filing.failed || 0) > 0 && (
                      <Tag color="red" style={{ marginTop: 4 }}>失败 {batchResult.results.filing.failed} 项</Tag>
                    )}
                  </Card>
                </Col>
              )}
            </Row>
            {batchResult.results?.invoice && (
              <Row gutter={16} style={{ marginTop: 12 }}>
                <Col span={12}>
                  <Card size="small" style={{ background: '#fef3c7' }}>
                    <Statistic
                      title="批量开票"
                      value={batchResult.results.invoice.success || 0}
                      suffix={`/ ${batchResult.results.invoice.total || 0}`}
                      valueStyle={{ color: (batchResult.results.invoice.failed || 0) > 0 ? '#d97706' : '#16a34a' }}
                    />
                    {(batchResult.results.invoice.failed || 0) > 0 && (
                      <Tag color="red" style={{ marginTop: 4 }}>失败 {batchResult.results.invoice.failed} 项</Tag>
                    )}
                  </Card>
                </Col>
              </Row>
            )}
            {(!batchResult.results?.filing?.total && !batchResult.results?.invoice?.total) && (
              <div style={{ textAlign: 'center', padding: 20, color: '#94a3b8' }}>
                当前无待处理任务，所有客户均已处理完毕
              </div>
            )}
          </div>
        ) : null}
      </Modal>

      {/* ===== 数据明细 Tab ===== */}
      <Card size="small" style={{ marginTop: 12 }} title={<Text strong style={{ fontSize: 13 }}>财税数据明细</Text>}>
        <Tabs items={[
          {
            key: 'vouchers', label: `近期凭证 (${vouchers.length})`,
            children: (
              <Table dataSource={vouchers} columns={[
                { title: '凭证号', dataIndex: 'voucher_no', width: 140 },
                { title: '日期', dataIndex: 'voucher_date', width: 100 },
                { title: '摘要', dataIndex: 'summary', ellipsis: true },
                { title: '借方合计', dataIndex: 'total_debit', width: 110, align: 'right' as const, render: (v: number) => v ? `¥${v.toLocaleString()}` : '-' },
                { title: '贷方合计', dataIndex: 'total_credit', width: 110, align: 'right' as const, render: (v: number) => v ? `¥${v.toLocaleString()}` : '-' },
                { title: '状态', dataIndex: 'status', width: 80, render: (s: string) => <Tag color={s === 'confirmed' ? 'green' : 'default'}>{s === 'confirmed' ? '已确认' : s}</Tag> },
              ]} rowKey="id" size="small" pagination={false} scroll={{ y: 280 }}
                locale={{ emptyText: <div style={{ padding: 20 }}><InboxOutlined style={{ fontSize: 32 }} /><div>暂无凭证</div></div> }} />
            ),
          },
          {
            key: 'documents', label: `近期票据 (${documents.length})`,
            children: (
              <Table dataSource={documents} columns={[
                { title: '文件名', dataIndex: 'file_name', ellipsis: true },
                { title: '类型', dataIndex: 'doc_type', width: 80, render: (t: string) => <Tag>{t}</Tag> },
                { title: 'OCR', dataIndex: 'ocr_status', width: 80, render: (s: string) => <Tag color={s === 'done' ? 'green' : 'orange'}>{s === 'done' ? '已识别' : '待处理'}</Tag> },
              ]} rowKey="id" size="small" pagination={false} scroll={{ y: 280 }}
                locale={{ emptyText: <div style={{ padding: 20 }}><InboxOutlined style={{ fontSize: 32 }} /><div>暂无票据</div></div> }} />
            ),
          },
          {
            key: 'filings', label: `近期申报 (${filings.length})`,
            children: (
              <Table dataSource={filings} columns={[
                { title: '税种', dataIndex: 'tax_type', width: 100, render: (t: string) => {
                  const m: Record<string, string> = { vat: '增值税', corporate_income: '企业所得税', stamp_duty: '印花税', surtax: '附加税' }
                  return <Tag color="blue">{m[t] || t}</Tag>
                }},
                { title: '所属期', dataIndex: 'period', width: 90 },
                { title: '状态', dataIndex: 'status', width: 90, render: (s: string) => {
                  const m: Record<string, { color: string; text: string }> = {
                    pending: { color: 'orange', text: '待申报' }, submitted: { color: 'blue', text: '已提交' },
                    success: { color: 'green', text: '申报成功' }, failed: { color: 'red', text: '失败' },
                  }
                  return <Tag color={(m[s] || {}).color}>{(m[s] || {}).text || s}</Tag>
                }},
              ]} rowKey="id" size="small" pagination={false} scroll={{ y: 280 }}
                locale={{ emptyText: <div style={{ padding: 20 }}><InboxOutlined style={{ fontSize: 32 }} /><div>暂无申报</div></div> }} />
            ),
          },
        ]} />
      </Card>
    </div>
  )
}
