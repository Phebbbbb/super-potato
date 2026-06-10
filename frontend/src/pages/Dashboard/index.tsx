import { useEffect, useState } from 'react'
import { Row, Col, Card, Statistic, Table, Spin, Tag, Typography, Button, App, Progress, Tooltip, Space, Modal, Steps, Form, Input, List } from 'antd'
import {
  ThunderboltOutlined, SyncOutlined, CheckCircleOutlined,
  CloudUploadOutlined, ScanOutlined, BookOutlined, FormOutlined, FileDoneOutlined,
  ClockCircleOutlined, InboxOutlined, CustomerServiceOutlined,
  RiseOutlined, FallOutlined, ArrowUpOutlined, ArrowDownOutlined,
  FileTextOutlined, AuditOutlined, WarningOutlined, SendOutlined,
  RobotOutlined, FundOutlined, BulbOutlined, DashboardOutlined,
  SafetyCertificateOutlined, SettingOutlined, BankOutlined,
} from '@ant-design/icons'
import { reportApi, voucherApi, documentApi, filingApi, announcementApi, batchApi, rpaApi, precheckApi, learningApi, anomalyApi, priorityApi, interactionApi, predictiveApi } from '@/services/api'
import { useClient } from '@/contexts/ClientContext'
import { useRole } from '@/hooks/useRole'
import { useNavigate } from 'react-router-dom'
import dayjs from 'dayjs'

const { Title, Text } = Typography

// ===== 迷你趋势条 =====
function MiniSpark({ data, color = '#2563eb', height = 40 }: { data: number[]; color?: string; height?: number }) {
  const max = Math.max(...data, 1)
  const min = Math.min(...data, 0)
  const range = max - min || 1
  const points = data.map((v, i) => `${(i / (data.length - 1)) * 100},${100 - ((v - min) / range) * 80 - 10}`).join(' ')
  return (
    <svg width="100%" height={height} style={{ display: 'block' }}>
      <polyline points={points} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      {data.map((v, i) => (
        <circle key={i} cx={`${(i / (data.length - 1)) * 100}%`} cy={`${100 - ((v - min) / range) * 80 - 10}%`} r="3" fill={i === data.length - 1 ? color : '#fff'} stroke={color} strokeWidth="1.5" />
      ))}
    </svg>
  )
}

// ===== 脉冲动画指示灯 =====
function PulseDot({ active, color = '#16a34a' }: { active: boolean; color?: string }) {
  return (
    <span style={{
      display: 'inline-block', width: 8, height: 8, borderRadius: 4,
      background: color, marginRight: 6,
      animation: active ? 'pulse 1.5s ease-in-out infinite' : 'none',
      opacity: active ? 1 : 0.4,
    }} />
  )
}

export default function Dashboard() {
  const [loading, setLoading] = useState(true)
  const [dash, setDash] = useState<any>(null)
  const [vouchers, setVouchers] = useState<any[]>([])
  const [documents, setDocuments] = useState<any[]>([])
  const [filings, setFilings] = useState<any[]>([])
  const [announcements, setAnnouncements] = useState<any[]>([])
  const [autoRate, setAutoRate] = useState<any>(null)
  const [precheck, setPrecheck] = useState<any>(null)
  const [anomaly, setAnomaly] = useState<any>(null)
  const [learningStats, setLearningStats] = useState<any>(null)
  const [priority, setPriority] = useState<any>(null)
  const [cliffCheck, setCliffCheck] = useState<any>(null)
  const [predictive, setPredictive] = useState<any>(null)
  const [precheckLoading, setPrecheckLoading] = useState(false)
  const { currentClientId } = useClient()
  const { isClient } = useRole()
  const navigate = useNavigate()
  const { message } = App.useApp()

  // ===== 批量操作 =====
  const [batchRunning, setBatchRunning] = useState(false)
  const [batchType, setBatchType] = useState('')
  const [batchResult, setBatchResult] = useState<any>(null)
  const [batchModalOpen, setBatchModalOpen] = useState(false)
  const [periodClosing, setPeriodClosing] = useState(false)
  const [feedbackSending, setFeedbackSending] = useState(false)
  const [feedbackModalOpen, setFeedbackModalOpen] = useState(false)
  const [feedbackForm] = Form.useForm()

  const fetchData = () => {
    setLoading(true)
    const params = { page_size: 20, client_id: currentClientId || undefined }
    Promise.all([
      reportApi.dashboard(),
      voucherApi.list({ page: 1, page_size: 20, client_id: currentClientId || undefined }),
      documentApi.list({ ...params, page: 1 }),
      filingApi.list({ ...params, page: 1 }),
      announcementApi.list(5),
      reportApi.automationRate(),
    ]).then(([dashRes, vRes, dRes, fRes, aRes, arRes]: any[]) => {
      setDash(dashRes)
      setVouchers(vRes?.items || [])
      setDocuments(dRes?.items || [])
      setFilings(fRes?.items || [])
      setAnnouncements(aRes?.items || [])
      setAutoRate(arRes)
      setLoading(false)
    }).catch(() => setLoading(false))
  }

  const fetchAlgorithmResults = async () => {
    if (!currentClientId) return
    setPrecheckLoading(true)
    try {
      const [pc, cc, ls, an, pr, pd]: any[] = await Promise.all([
        precheckApi.check(currentClientId),
        precheckApi.cliffCheck(currentClientId),
        learningApi.stats(),
        anomalyApi.check(currentClientId),
        priorityApi.client(currentClientId),
        predictiveApi.summary(currentClientId).catch(() => null),
      ])
      setPrecheck(pc); setCliffCheck(cc); setLearningStats(ls); setAnomaly(an); setPriority(pr); setPredictive(pd)
    } catch { /* ignore */ }
    setPrecheckLoading(false)
  }

  useEffect(() => { fetchData(); fetchAlgorithmResults() }, [currentClientId])

  // ===== 批量自动化 =====
  const handleBatchAll = async (operation: string) => {
    setBatchRunning(true)
    setBatchType(operation === 'filing' ? '批量申报' : operation === 'invoice' ? '批量开票' : '全流程自动化')
    setBatchModalOpen(true)
    setBatchResult(null)
    try {
      const res: any = await batchApi.batchAllClients(operation)
      setBatchResult(res)
      if (res.results?.filing?.success > 0 || res.results?.invoice?.success > 0) {
        message.success(`批量操作完成`)
      } else {
        message.info('当前无待处理任务')
      }
      fetchData()
    } catch (e: any) { message.error(e?.detail || '批量操作失败') }
    setBatchRunning(false)
  }

  const handlePeriodClose = () => {
    Modal.confirm({
      title: '一键关账',
      content: '将自动执行：折旧计提 → 收入结转 → 费用结转 → 所得税预估 → 申报创建。确认继续？',
      onOk: async () => {
        setPeriodClosing(true)
        try {
          const res: any = await rpaApi.periodClose(currentClientId!)
          message.success(`关账完成 — 收入 ¥${res.summary?.total_revenue?.toLocaleString()} | 创建 ${res.summary?.filings_created} 项申报`)
          fetchData()
        } catch (e: any) { message.error(e?.detail || '关账失败') }
        setPeriodClosing(false)
      },
    })
  }

  if (loading || !dash) return <Spin spinning><div style={{ height: 400 }} /></Spin>

  // ==================== 客户端视图 ====================
  if (isClient) {
    const docTotal = documents.length
    const docDone = documents.filter((d: any) => d.ocr_status === 'done').length
    const vTotal = vouchers.length
    const vConfirmed = vouchers.filter((v: any) => v.status === 'confirmed').length
    const fTotal = filings.length
    const fSubmitted = filings.filter((f: any) => f.status === 'success' || f.status === 'submitted').length
    const currentStep = !docTotal ? 0 : docDone < docTotal ? 1 : !vTotal ? 2 : vConfirmed < vTotal ? 3 : fSubmitted >= fTotal ? 4 : 3

    const pipelineSteps = [
      { title: '上传票据', icon: <CloudUploadOutlined />, desc: '上传发票、收据等' },
      { title: 'AI 识别', icon: <ScanOutlined />, desc: 'OCR 智能识别' },
      { title: '生成凭证', icon: <BookOutlined />, desc: '自动生成记账凭证' },
      { title: '申报纳税', icon: <FormOutlined />, desc: '电子税务局申报' },
      { title: '完成归档', icon: <FileDoneOutlined />, desc: '凭证归档备查' },
    ]

    return (
      <div>
        <div style={{ marginBottom: 20 }}>
          <Title level={5} style={{ margin: 0 }}>财税业务进度</Title>
          <Text type="secondary" style={{ fontSize: 12 }}>全流程 AI 自动化处理 · 实时更新</Text>
        </div>

        <Card style={{ marginBottom: 16, borderRadius: 8 }}>
          <Steps
            current={currentStep}
            size="default"
            items={pipelineSteps.map((s, i) => ({
              title: s.title, description: s.desc,
              icon: i < currentStep ? <CheckCircleOutlined /> : i === currentStep ? <SyncOutlined spin /> : <ClockCircleOutlined />,
              status: (i < currentStep ? 'finish' : i === currentStep ? 'process' : 'wait') as any,
            }))}
          />
          <div style={{ marginTop: 20 }}>
            <Progress percent={Math.round((currentStep / 4) * 100)}
              strokeColor={{ '0%': '#2563eb', '100%': '#16a34a' }}
              format={() => ['开始上传', 'AI 处理中', '凭证生成', '申报提交', '全部完成'][currentStep]} />
          </div>
        </Card>

        <Row gutter={[12, 12]}>
          {[
            { label: '已上传票据', value: docTotal, suffix: '张', icon: <CloudUploadOutlined />, color: '#2563eb', path: '/documents' },
            { label: 'AI 已识别', value: `${docDone}/${docTotal}`, suffix: '', icon: <ScanOutlined />, color: '#7c3aed', path: '/documents' },
            { label: '记账凭证', value: vTotal, suffix: '张', icon: <BookOutlined />, color: '#d97706', path: '/vouchers' },
            { label: '已申报', value: `${fSubmitted}/${fTotal}`, suffix: '', icon: <CheckCircleOutlined />, color: '#16a34a', path: '/tax-filings' },
          ].map((item, i) => (
            <Col xs={12} sm={6} key={i}>
              <Card size="small" hoverable onClick={() => navigate(item.path)} style={{ textAlign: 'center' }}>
                <div style={{ fontSize: 24, color: item.color, marginBottom: 4 }}>{item.icon}</div>
                <Statistic title={item.label} value={item.value} suffix={item.suffix}
                  valueStyle={{ color: item.color, fontSize: 24, fontWeight: 700 }} />
              </Card>
            </Col>
          ))}
        </Row>

        {currentStep === 0 && (
          <Card style={{ marginTop: 16, background: 'linear-gradient(135deg, #eff6ff 0%, #faf5ff 100%)', borderColor: '#bfdbfe', textAlign: 'center' }}>
            <InboxOutlined style={{ fontSize: 48, color: '#2563eb', marginBottom: 12 }} />
            <div style={{ fontSize: 16, fontWeight: 600, color: '#1e3a5f', marginBottom: 8 }}>开始您的财税自动化之旅</div>
            <div style={{ fontSize: 13, color: '#64748b', marginBottom: 16 }}>上传发票、收据等原始凭证，AI 将自动完成识别、记账、申报全流程</div>
            <Button type="primary" size="large" icon={<CloudUploadOutlined />} onClick={() => navigate('/documents')}>前往上传票据</Button>
          </Card>
        )}

        {currentStep > 0 && currentStep < 4 && (
          <Card style={{ marginTop: 16, background: '#fffbeb', borderColor: '#fde68a', textAlign: 'center' }}>
            <SyncOutlined spin style={{ fontSize: 32, color: '#d97706', marginBottom: 8 }} />
            <div style={{ fontSize: 14, color: '#92400e' }}>
              AI 正在处理您的财税数据，当前阶段：<Tag color="gold" style={{ marginLeft: 6 }}>{pipelineSteps[currentStep].title}</Tag>
            </div>
            <div style={{ fontSize: 12, color: '#a16207', marginTop: 4 }}>服务端操作人员正在复核，完成后将自动进入下一阶段</div>
          </Card>
        )}

        {currentStep >= 4 && (
          <Card style={{ marginTop: 16, background: 'linear-gradient(135deg, #f0fdf4 0%, #ecfdf5 100%)', borderColor: '#bbf7d0', textAlign: 'center' }}>
            <CheckCircleOutlined style={{ fontSize: 48, color: '#16a34a', marginBottom: 12 }} />
            <div style={{ fontSize: 16, fontWeight: 600, color: '#166534' }}>本期财税处理全部完成</div>
            <div style={{ fontSize: 13, color: '#4ade80', marginTop: 4 }}>凭证已归档，申报已完成，请妥善保管相关凭据</div>
          </Card>
        )}

        <Card size="small" style={{ marginTop: 16, background: '#faf5ff', borderColor: '#e9d5ff' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <Text strong style={{ fontSize: 13 }}>需要帮助？</Text>
              <Text type="secondary" style={{ fontSize: 12, marginLeft: 8 }}>发送消息联系服务端财税专家</Text>
            </div>
            <Button type="primary" size="small" icon={<CustomerServiceOutlined />}
              onClick={() => { feedbackForm.resetFields(); setFeedbackModalOpen(true) }}>联系客服</Button>
          </div>
        </Card>

        <Modal title="联系服务端财税专家" open={feedbackModalOpen} onCancel={() => setFeedbackModalOpen(false)}
          onOk={async () => {
            const values = await feedbackForm.validateFields()
            setFeedbackSending(true)
            try { await interactionApi.feedback(values); message.success('反馈已发送'); setFeedbackModalOpen(false) }
            catch { message.error('发送失败') }
            setFeedbackSending(false)
          }} confirmLoading={feedbackSending} okText="发送">
          <Form form={feedbackForm} layout="vertical">
            <Form.Item label="标题" name="title" rules={[{ required: true }]}><Input placeholder="如：咨询申报进度" maxLength={100} /></Form.Item>
            <Form.Item label="内容" name="message" rules={[{ required: true }]}><Input.TextArea rows={4} placeholder="描述您的问题或需求" maxLength={500} /></Form.Item>
          </Form>
        </Modal>

        <Card size="small" style={{ marginTop: 16 }} title="近期动态">
          <Table dataSource={[...documents.slice(0, 3), ...vouchers.slice(0, 3)]} columns={[
            { title: '类型', dataIndex: 'doc_type', width: 80, render: (_: any, r: any) => <Tag>{r.doc_type || '凭证'}</Tag> },
            { title: '名称', render: (_: any, r: any) => <Text ellipsis style={{ maxWidth: 200 }}>{r.file_name || r.voucher_no || r.summary}</Text> },
            { title: '时间', dataIndex: 'created_at', width: 140, render: (v: string) => v?.slice(0, 16) },
          ]} rowKey="id" size="small" pagination={false} locale={{ emptyText: '暂无数据' }} />
        </Card>
      </div>
    )
  }

  // ==================== 服务端视图 ====================
  const cm = dash.current_month || {}
  const ops = dash.operations || {}
  const bal = dash.balance || {}
  const revenueData = (dash.trends?.revenue || []).map((r: any) => r.revenue)
  const taxData = (dash.trends?.tax_burden || []).map((r: any) => r.tax_burden)
  const docProcessRate = ops.total_documents > 0 ? Math.round((ops.documents_processed / ops.total_documents) * 100) : 0
  const automationPct = autoRate?.overall_automation_pct || 0

  // 引擎状态汇总
  const engineChecks = [
    { label: '预检引擎', ok: precheck?.grade === 'excellent' || precheck?.grade === 'good', detail: precheck ? `${precheck.score}分·${precheck.grade === 'excellent' ? '优秀' : precheck.grade === 'good' ? '良好' : '预警'}` : '--' },
    { label: '异常检测', ok: anomaly?.risk_level !== 'critical', detail: anomaly ? `${anomaly.risk_score}分` : '--' },
    { label: '自学习', ok: (learningStats?.high_confidence_patterns || 0) > 0, detail: learningStats ? `${learningStats.total_patterns_learned || 0}条模式` : '--' },
    { label: 'CIT悬崖', ok: cliffCheck?.alert !== 'warning', detail: cliffCheck?.alert === 'warning' ? '需关注' : '安全' },
    { label: '智能优先级', ok: priority?.priority_level !== 'critical', detail: priority ? priority.priority_level === 'high' ? '优先' : '正常' : '--' },
    { label: '预测引擎', ok: predictive?.risk_level !== 'critical', detail: predictive ? (predictive.revenue_trend === 'up' ? '↑' : predictive.revenue_trend === 'down' ? '↓' : '→') + ' ' + (predictive.risk_level || '--') : '--' },
  ]

  return (
    <div>
      {/* ===== 脉冲动画样式 ===== */}
      <style>{`@keyframes pulse { 0%,100% { opacity:1; } 50% { opacity:0.3; } }`}</style>

      {/* ===== 顶部：AI 引擎状态条 ===== */}
      <div style={{
        background: 'linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #172554 100%)',
        borderRadius: 10, padding: '16px 20px', marginBottom: 16,
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        flexWrap: 'wrap', gap: 12,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{
            width: 36, height: 36, borderRadius: 8,
            background: 'linear-gradient(135deg, #2563eb, #7c3aed)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <RobotOutlined style={{ fontSize: 18, color: '#fff' }} />
          </div>
          <div>
            <Text strong style={{ color: '#f1f5f9', fontSize: 18, letterSpacing: 2, fontFamily: "'ZCOOL KuaiLe', 'Ma Shan Zheng', cursive" }}>爻一爻 · 智能财税大脑</Text>
            <div style={{ fontSize: 11, color: '#94a3b8' }}>
              <PulseDot active color="#22c55e" />
              {automationPct >= 80 ? '全自动运行中' : 'AI 引擎就绪'}
              <span style={{ marginLeft: 12, color: '#64748b' }}>{dayjs().format('YYYY年M月D日 HH:mm')}</span>
            </div>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
          {engineChecks.map((e, i) => (
            <Tooltip key={i} title={`${e.label}: ${e.detail}`}>
              <div style={{ textAlign: 'center', cursor: 'default' }}>
                <PulseDot active={e.ok} color={e.ok ? '#22c55e' : '#f59e0b'} />
                <Text style={{ color: e.ok ? '#94a3b8' : '#fbbf24', fontSize: 10, display: 'block' }}>{e.label}</Text>
              </div>
            </Tooltip>
          ))}
          <Button size="small" ghost loading={precheckLoading} onClick={fetchAlgorithmResults}
            style={{ borderColor: '#475569', color: '#94a3b8', fontSize: 11 }}>
            刷新引擎
          </Button>
        </div>
      </div>

      {/* ===== 核心 KPI 条 ===== */}
      <Row gutter={[12, 12]} style={{ marginBottom: 12 }}>
        {[
          { label: '本月收入', value: cm.revenue || 0, color: '#16a34a', icon: <RiseOutlined />, path: '/reports' },
          { label: '毛利', value: cm.gross_profit || 0, color: cm.gross_profit >= 0 ? '#16a34a' : '#dc2626', icon: cm.gross_profit >= 0 ? <ArrowUpOutlined /> : <ArrowDownOutlined />, path: '/reports', sub: `利润率 ${cm.profit_margin || 0}%` },
          { label: '应缴增值税', value: cm.vat_payable || 0, color: cm.vat_payable > 0 ? '#d97706' : '#64748b', icon: <BankOutlined />, path: '/tax-filings', sub: `销项${(cm.output_vat || 0).toLocaleString()} - 进项${(cm.input_vat || 0).toLocaleString()}` },
          { label: '预缴所得税', value: cm.est_cit || 0, color: '#2563eb', icon: <FileTextOutlined />, path: '/tax-filings', sub: '按小微企业 2.5% 估算' },
          { label: '自动化率', value: `${automationPct}%`, color: automationPct >= 80 ? '#16a34a' : '#d97706', icon: <ThunderboltOutlined />, path: '/settings', sub: `${autoRate?.fully_auto_clients || 0}/${autoRate?.total_clients || 0} 户全自动` },
          { label: '票据处理率', value: `${docProcessRate}%`, color: docProcessRate >= 80 ? '#16a34a' : '#d97706', icon: <ScanOutlined />, path: '/documents', sub: `待处理 ${ops.total_documents - ops.documents_processed || 0} 张` },
        ].map((kpi, i) => (
          <Col xs={12} sm={8} md={4} key={i}>
            <Card
              size="small"
              hoverable
              onClick={() => navigate(kpi.path)}
              style={{ borderTop: `2px solid ${kpi.color}`, borderRadius: 6 }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div>
                  <Text style={{ fontSize: 11, color: '#94a3b8' }}>{kpi.label}</Text>
                  <div style={{ fontSize: 22, fontWeight: 700, color: kpi.color, marginTop: 2 }}>
                    {typeof kpi.value === 'number' ? `¥${kpi.value.toLocaleString()}` : kpi.value}
                  </div>
                  {kpi.sub && <Text style={{ fontSize: 10, color: '#94a3b8' }}>{kpi.sub}</Text>}
                </div>
                <div style={{ fontSize: 18, color: kpi.color, opacity: 0.6 }}>{kpi.icon}</div>
              </div>
            </Card>
          </Col>
        ))}
      </Row>

      {/* ===== 第二行：自动化工坊（全宽，核心） ===== */}
      <Card
        size="small"
        style={{ marginTop: 12, borderRadius: 8, background: 'linear-gradient(135deg, #faf5ff 0%, #f5f3ff 50%, #eff6ff 100%)', borderColor: '#c4b5fd' }}
        title={
          <Space>
            <ThunderboltOutlined style={{ color: '#7c3aed' }} />
            <Text strong style={{ fontSize: 14 }}>自动化工坊</Text>
            <Tag color="purple" style={{ fontSize: 10 }}>
              当前自动化率 {automationPct}%
            </Tag>
          </Space>
        }
        extra={
          <Space size={4}>
            <Text type="secondary" style={{ fontSize: 11 }}>自动关账：每月 28 日 22:00</Text>
            <Text type="secondary" style={{ fontSize: 11 }}>自动申报：每月 10 日 08:00</Text>
          </Space>
        }
      >
        <Row gutter={[16, 0]} align="middle">
          <Col flex="auto">
            <Space size={12} wrap>
              <Button type="primary" icon={<SendOutlined />}
                loading={batchRunning && batchType === '批量申报'}
                onClick={() => handleBatchAll('filing')}
                style={{ background: '#7c3aed', borderColor: '#7c3aed' }}>
                一键全客户批量申报
              </Button>
              <Button icon={<FileTextOutlined />}
                loading={batchRunning && batchType === '批量开票'}
                onClick={() => handleBatchAll('invoice')}
                style={{ borderColor: '#d97706', color: '#d97706' }}>
                一键全客户批量开票
              </Button>
              <Button icon={<SyncOutlined />}
                loading={batchRunning && batchType === '全流程自动化'}
                onClick={() => handleBatchAll('both')}
                style={{ borderColor: '#16a34a', color: '#16a34a' }}>
                一键申报+开票全流程
              </Button>
              <Button danger icon={<ThunderboltOutlined />}
                loading={periodClosing} onClick={handlePeriodClose}>
                一键期末关账
              </Button>
            </Space>
          </Col>
          <Col>
            <Space size={16}>
              <Statistic title="最近执行" value={autoRate?.last_run_at ? dayjs(autoRate.last_run_at).format('MM/DD HH:mm') : '--'}
                valueStyle={{ fontSize: 14, color: '#64748b' }} />
              <Statistic title="全自动客户" value={autoRate?.fully_auto_clients || 0} suffix={`/${autoRate?.total_clients || 0}`}
                valueStyle={{ fontSize: 14, color: '#7c3aed' }} />
            </Space>
          </Col>
        </Row>
      </Card>

      {/* ===== 第三行：趋势 + 运营 + 快捷 ===== */}
      <Row gutter={[12, 12]} style={{ marginTop: 12 }}>
        <Col xs={24} md={14}>
          <Card size="small" title={<Text strong style={{ fontSize: 13 }}>收入与税负趋势</Text>} style={{ borderRadius: 8 }}>
            <Row gutter={16}>
              <Col span={12}>
                <Text style={{ fontSize: 11, color: '#94a3b8' }}>月度收入</Text>
                <MiniSpark data={revenueData.length > 0 ? revenueData : [0, 0, 0]} color="#2563eb" height={56} />
                <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 2 }}>
                  {(dash.trends?.revenue || []).slice(-3).map((r: any, i: number) => (
                    <Text key={i} style={{ fontSize: 10, color: '#64748b' }}>
                      ¥{r.revenue > 10000 ? `${(r.revenue / 10000).toFixed(1)}w` : r.revenue}
                    </Text>
                  ))}
                </div>
              </Col>
              <Col span={12}>
                <Text style={{ fontSize: 11, color: '#94a3b8' }}>税负率 %</Text>
                <MiniSpark data={taxData.length > 0 ? taxData : [0, 0, 0]} color="#d97706" height={56} />
                <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 2 }}>
                  {(dash.trends?.tax_burden || []).slice(-3).map((r: any, i: number) => (
                    <Text key={i} style={{ fontSize: 10, color: r.tax_burden > 5 ? '#dc2626' : '#64748b' }}>{r.tax_burden}%</Text>
                  ))}
                </div>
              </Col>
            </Row>
          </Card>
        </Col>
        <Col xs={24} md={10}>
          <Card size="small" title={<Text strong style={{ fontSize: 13 }}>运营总览</Text>} style={{ borderRadius: 8 }}>
            <Row gutter={[12, 12]}>
              {[
                { label: '本月凭证', value: ops.vouchers_this_month || 0, suffix: '张' },
                { label: '待申报', value: ops.pending_filings || 0, suffix: '项', alert: true },
                { label: '已申报', value: ops.submitted_filings || 0, suffix: '项', ok: true },
                { label: '累计凭证', value: ops.total_vouchers || 0, suffix: '张' },
              ].map((m, i) => (
                <Col span={12} key={i}>
                  <Statistic
                    title={<Text style={{ fontSize: 11 }}>{m.label}</Text>}
                    value={m.value}
                    suffix={m.suffix}
                    valueStyle={{
                      fontSize: 20, fontWeight: 700,
                      color: m.alert && m.value > 0 ? '#dc2626' : m.ok ? '#16a34a' : '#1e293b',
                    }}
                  />
                </Col>
              ))}
            </Row>
          </Card>
        </Col>
      </Row>

      {/* ===== 预测分析快报 ===== */}
      {predictive && predictive.revenue_next_month > 0 && (
        <Card size="small" style={{ marginTop: 12, borderRadius: 8, background: 'linear-gradient(90deg, #f0f9ff 0%, #ecfeff 100%)', borderColor: '#bae6fd' }}>
          <Row gutter={16} align="middle">
            <Col flex="auto">
              <Space size={4}>
                <FundOutlined style={{ color: '#0284c7' }} />
                <Text strong style={{ fontSize: 13 }}>AI 预测引擎</Text>
                <Tag color={predictive.data_confidence === 'high' ? 'green' : predictive.data_confidence === 'medium' ? 'blue' : 'default'} style={{ fontSize: 10 }}>
                  {predictive.data_confidence === 'high' ? '高置信度' : predictive.data_confidence === 'medium' ? '中置信度' : '数据积累中'}
                </Tag>
              </Space>
            </Col>
            <Col>
              <Text style={{ fontSize: 12, color: '#0284c7' }}>
                下月预估收入 <Text strong style={{ fontSize: 16 }}>¥{predictive.revenue_next_month?.toLocaleString()}</Text>
                <span style={{ marginLeft: 8, color: predictive.revenue_trend === 'up' ? '#16a34a' : predictive.revenue_trend === 'down' ? '#dc2626' : '#64748b' }}>
                  {predictive.revenue_trend === 'up' ? '↑' : predictive.revenue_trend === 'down' ? '↓' : '→'} {Math.abs(predictive.revenue_trend_pct || 0).toFixed(1)}%
                </span>
              </Text>
            </Col>
            <Col>
              <Text style={{ fontSize: 12, color: '#64748b' }}>
                未来6月税负 <Text strong style={{ fontSize: 16, color: '#d97706' }}>¥{predictive.tax_next_6m?.toLocaleString()}</Text>
              </Text>
            </Col>
            <Col>
              <Tooltip title={predictive.top_recommendation || ''}>
                <Tag color={predictive.risk_level === 'critical' ? 'red' : predictive.risk_level === 'high' ? 'orange' : predictive.risk_level === 'medium' ? 'gold' : 'green'}>
                  风险: {predictive.risk_level?.toUpperCase() || '--'} ({predictive.risk_score || 0}分)
                </Tag>
              </Tooltip>
            </Col>
          </Row>
        </Card>
      )}

      {/* ===== 第三行：快捷操作 ===== */}
      <Row gutter={[12, 12]} style={{ marginTop: 12 }}>
        <Col xs={24} md={12}>
          <Card size="small" title={<Text strong style={{ fontSize: 13 }}>快捷入口</Text>} style={{ borderRadius: 8 }}>
            <Space direction="vertical" style={{ width: '100%' }} size={8}>
              {[
                { icon: <FileTextOutlined />, label: '票据采集录入', path: '/documents' },
                { icon: <AuditOutlined />, label: 'AI 智能记账', path: '/vouchers' },
                { icon: <CheckCircleOutlined />, label: '申报任务', path: '/tax-filings', badge: ops.pending_filings },
                { icon: <WarningOutlined />, label: '税务风险自查', path: '/tax-risk' },
                { icon: <RobotOutlined />, label: 'AI 税务顾问', path: '/ai-agent' },
              ].map((btn, i) => (
                <Button key={i} block icon={btn.icon} onClick={() => navigate(btn.path)} style={{ textAlign: 'left' }}>
                  {btn.label}
                  {btn.badge && btn.badge > 0 && <Tag color="red" style={{ marginLeft: 8, fontSize: 10 }}>{btn.badge}</Tag>}
                </Button>
              ))}
            </Space>
          </Card>
        </Col>

        {/* 公告栏 */}
        <Col xs={24} md={12}>
          <Card size="small" title={<Text strong style={{ fontSize: 13 }}>最新政策</Text>}
            extra={<Button size="small" onClick={async () => {
              try {
                const res: any = await announcementApi.list(20)
                setAnnouncements(res.items || [])
              } catch { /* ignore */ }
            }}>更多</Button>}
            style={{ borderRadius: 8 }}>
            {announcements.length === 0 ? (
              <div style={{ textAlign: 'center', padding: 24, color: '#94a3b8' }}>
                <BulbOutlined style={{ fontSize: 28, marginBottom: 8 }} />
                <div style={{ fontSize: 12 }}>暂无最新政策公告</div>
              </div>
            ) : (
              <List
                dataSource={announcements}
                size="small"
                renderItem={(item: any) => (
                  <List.Item
                    style={{ padding: '6px 0', borderBottom: '1px solid #f1f5f9', cursor: 'pointer' }}
                    onClick={() => { if (item.url) window.open(item.url, '_blank') }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, width: '100%' }}>
                      <BulbOutlined style={{ color: '#f59e0b', fontSize: 12 }} />
                      <Text ellipsis style={{ flex: 1, fontSize: 12 }}>{item.title}</Text>
                      <Text style={{ fontSize: 10, color: '#94a3b8', flexShrink: 0 }}>{item.pub_date || item.publish_date || ''}</Text>
                    </div>
                  </List.Item>
                )}
              />
            )}
          </Card>
        </Col>

      </Row>


      {/* ===== 批量结果弹窗 ===== */}
      <Modal title={`批量操作结果 — ${batchType}`} open={batchModalOpen}
        onCancel={() => setBatchModalOpen(false)}
        footer={<Button onClick={() => setBatchModalOpen(false)}>关闭</Button>} width={600}>
        {batchRunning ? (
          <div style={{ textAlign: 'center', padding: 40 }}>
            <Spin size="large" />
            <div style={{ marginTop: 16, fontSize: 14, color: '#64748b' }}>正在并行处理多客户任务…</div>
          </div>
        ) : batchResult ? (
          <Row gutter={16}>
            <Col span={12}>
              <Statistic title="客户总数" value={batchResult.clients_count} suffix="户" />
            </Col>
            {batchResult.results?.filing && (
              <Col span={12}>
                <Statistic title="批量申报"
                  value={batchResult.results.filing.success || 0}
                  suffix={`/ ${batchResult.results.filing.total || 0}`}
                  valueStyle={{ color: (batchResult.results.filing.failed || 0) > 0 ? '#d97706' : '#16a34a' }} />
              </Col>
            )}
            {batchResult.results?.invoice && (
              <Col span={12} style={{ marginTop: 12 }}>
                <Statistic title="批量开票"
                  value={batchResult.results.invoice.success || 0}
                  suffix={`/ ${batchResult.results.invoice.total || 0}`}
                  valueStyle={{ color: (batchResult.results.invoice.failed || 0) > 0 ? '#d97706' : '#16a34a' }} />
              </Col>
            )}
            {!batchResult.results?.filing?.total && !batchResult.results?.invoice?.total && (
              <Col span={24}><div style={{ textAlign: 'center', padding: 20, color: '#94a3b8' }}>当前无待处理任务</div></Col>
            )}
          </Row>
        ) : null}
      </Modal>
    </div>
  )
}
