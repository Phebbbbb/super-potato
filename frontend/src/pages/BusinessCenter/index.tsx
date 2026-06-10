import { useState, useEffect, useRef } from 'react'
import {
  Card, Table, Button, Space, Tag, Modal, Form, Input, Select,
  InputNumber, DatePicker, App, Statistic, Row, Col, Typography, Alert,
  Empty, Popconfirm, Descriptions, Spin, Tabs,
} from 'antd'
import {
  PlusOutlined, FileProtectOutlined, BankOutlined, CloseCircleOutlined,
  SwapOutlined, AuditOutlined, GlobalOutlined, CheckCircleOutlined,
  ExportOutlined, ReloadOutlined, SearchOutlined, ThunderboltOutlined,
  CopyOutlined, BulbOutlined, CrownOutlined, SafetyCertificateOutlined,
  SendOutlined, UserOutlined, EyeOutlined,
} from '@ant-design/icons'
import { useClient } from '@/contexts/ClientContext'
import api, { auditApi } from '@/services/api'
import dayjs from 'dayjs'

const { Text, Title, Paragraph } = Typography
const { TextArea } = Input

const OFFICIAL_URLS = {
  gsxt: 'https://www.gsxt.gov.cn/',
  registration: 'https://zwfw.samr.gov.cn/',
  deregistration: 'https://www.gsxt.gov.cn/corp-query-homepage.html',
  equity: 'https://www.gsxt.gov.cn/corp-query-homepage.html',
}

const TYPE_LABELS: Record<string, string> = {
  annual_report: '工商年报',
  company_registration: '公司注册',
  company_deregistration: '公司注销',
  equity_change: '股权变更',
}

// ===== 工商年报 Tab =====
function AnnualReportTab() {
  const [reports, setReports] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [detailOpen, setDetailOpen] = useState(false)
  const [selected, setSelected] = useState<any>(null)
  const [form] = Form.useForm()
  const { currentClientId } = useClient()
  const { message } = App.useApp()

  const fetchReports = async () => {
    if (!currentClientId) return
    setLoading(true)
    try {
      const res: any = await api.get('/annual-reports/', { params: { client_id: currentClientId } })
      setReports(res.items || [])
    } catch { /* ignore */ }
    setLoading(false)
  }

  useEffect(() => { fetchReports() }, [currentClientId])

  const handleCreate = async () => {
    const values = await form.validateFields()
    try {
      await api.post('/annual-reports/', { ...values, client_id: currentClientId })
      message.success('年报已创建')
      setCreateOpen(false); form.resetFields(); fetchReports()
    } catch (e: any) { message.error(e?.response?.data?.detail || '创建失败') }
  }

  const handleView = async (record: any) => {
    try {
      const res: any = await api.get(`/annual-reports/${record.id}`)
      setSelected(res)
      setDetailOpen(true)
    } catch { message.error('加载详情失败') }
  }

  const handleSubmit = async (record: any) => {
    Modal.confirm({
      title: '确认提交', content: `提交 ${record.report_year} 年度年报至市场监督管理局？`,
      onOk: async () => {
        try {
          await api.patch(`/annual-reports/${record.id}`, { status: 'submitted' })
          message.success('年报已提交'); fetchReports()
        } catch { message.error('提交失败') }
      },
    })
  }

  const handleDelete = async (record: any) => {
    Modal.confirm({
      title: '确认删除', content: `删除 ${record.report_year} 年度年报?`,
      onOk: async () => {
        try { await api.delete(`/annual-reports/${record.id}`); message.success('已删除'); fetchReports() }
        catch { message.error('删除失败') }
      },
    })
  }

  const statusMap: Record<string, { color: string; text: string }> = {
    draft: { color: 'orange', text: '草稿' },
    submitted: { color: 'blue', text: '已提交' },
    published: { color: 'green', text: '已公示' },
  }

  const currentYear = dayjs().year()
  const submittedCount = reports.filter(r => r.status === 'submitted' || r.status === 'published').length

  const columns = [
    { title: '年度', dataIndex: 'report_year', width: 80, render: (v: number) => <Text strong>{v}</Text> },
    { title: '企业名称', dataIndex: 'company_name', width: 180, ellipsis: true },
    { title: '信用代码', dataIndex: 'unified_social_credit_code', width: 160 },
    { title: '营业收入(万元)', dataIndex: 'annual_revenue', width: 120, align: 'right' as const, render: (v: any) => v ? Number(v).toLocaleString() : '-' },
    { title: '从业人数', dataIndex: 'employee_count', width: 80, align: 'right' as const },
    { title: '状态', dataIndex: 'status', width: 90, render: (s: string) => <Tag color={(statusMap[s] || {}).color}>{(statusMap[s] || {}).text || s}</Tag> },
    { title: '提交时间', dataIndex: 'submitted_at', width: 110, render: (v: string) => v ? dayjs(v).format('YYYY-MM-DD') : '-' },
    {
      title: '操作', width: 200,
      render: (_: any, r: any) => (
        <Space size={4} wrap>
          <Button size="small" icon={<EyeOutlined />} onClick={() => handleView(r)}>查看</Button>
          {r.status === 'draft' && (
            <>
              <Button size="small" icon={<CheckCircleOutlined />} onClick={() => handleSubmit(r)} style={{ color: '#16a34a', borderColor: '#16a34a' }}>提交</Button>
              <Button size="small" danger onClick={() => handleDelete(r)}>删除</Button>
            </>
          )}
        </Space>
      ),
    },
  ]

  return (
    <div>
      <Alert message="工商年报是企业每年向市场监督管理局提交的年度报告。逾期未报将被列入经营异常名录。" type="info" showIcon style={{ marginBottom: 16 }} />
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}><Card size="small"><Statistic title="年报总数" value={reports.length} suffix="份" /></Card></Col>
        <Col span={6}><Card size="small"><Statistic title="已提交/公示" value={submittedCount} suffix="份" valueStyle={{ color: '#16a34a' }} /></Card></Col>
        <Col span={6}><Card size="small"><Statistic title="草稿" value={reports.filter(r => r.status === 'draft').length} suffix="份" valueStyle={{ color: '#d97706' }} /></Card></Col>
        <Col span={6}>
          <Space wrap>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => { form.resetFields(); setCreateOpen(true) }}>创建年报</Button>
            <Button icon={<ThunderboltOutlined />} onClick={async () => {
              Modal.info({ title: '自动填报', content: '使用 Playwright 自动登录国家企业信用信息公示系统，自动填充年报数据。', onOk: async () => {
                try {
                  const res: any = await api.post('/business/auto/annual-report', {})
                  Modal.success({ title: '填报完成', content: res.message || '请前往官网确认提交', width: 500 })
                } catch (e: any) { message.error(e?.response?.data?.detail || '自动化失败') }
              }})
            }}>自动填报</Button>
            <Button icon={<GlobalOutlined />} href={OFFICIAL_URLS.gsxt} target="_blank">前往官网</Button>
          </Space>
        </Col>
      </Row>
      <Table rowKey="id" columns={columns} dataSource={reports} loading={loading} size="small" />
      <Modal title="创建工商年报" open={createOpen} onOk={handleCreate} onCancel={() => { setCreateOpen(false); form.resetFields() }} width={700}>
        <Form form={form} layout="vertical" initialValues={{ report_year: currentYear - 1 }}>
          <Space size={12}>
            <Form.Item label="报告年度" name="report_year" rules={[{ required: true }]}>
              <Select style={{ width: 120 }} options={[currentYear - 1, currentYear - 2].map(y => ({ label: `${y}年度`, value: y }))} />
            </Form.Item>
            <Form.Item label="企业名称" name="company_name" rules={[{ required: true }]}><Input style={{ width: 240 }} /></Form.Item>
            <Form.Item label="信用代码" name="unified_social_credit_code" rules={[{ required: true }]}><Input style={{ width: 200 }} /></Form.Item>
          </Space>
          <Space size={12}>
            <Form.Item label="资产总额(万元)" name="total_assets"><InputNumber style={{ width: 140 }} /></Form.Item>
            <Form.Item label="营业收入(万元)" name="annual_revenue"><InputNumber style={{ width: 140 }} /></Form.Item>
            <Form.Item label="利润总额(万元)" name="annual_profit"><InputNumber style={{ width: 140 }} /></Form.Item>
            <Form.Item label="净利润(万元)" name="annual_net_profit"><InputNumber style={{ width: 140 }} /></Form.Item>
          </Space>
          <Space size={12}>
            <Form.Item label="纳税总额(万元)" name="annual_tax_paid"><InputNumber style={{ width: 140 }} /></Form.Item>
            <Form.Item label="从业人数" name="employee_count"><InputNumber style={{ width: 100 }} /></Form.Item>
          </Space>
          <Form.Item label="经营范围" name="business_scope"><Input.TextArea rows={2} /></Form.Item>
        </Form>
      </Modal>
      <Modal title={`${selected?.report_year}年度 工商年报详情`} open={detailOpen} onCancel={() => setDetailOpen(false)} footer={<Button onClick={() => setDetailOpen(false)}>关闭</Button>} width={800}>
        {selected && (
          <Descriptions bordered size="small" column={2}>
            <Descriptions.Item label="报告年度">{selected.report_year}</Descriptions.Item>
            <Descriptions.Item label="状态"><Tag color={(statusMap[selected.status] || {}).color}>{(statusMap[selected.status] || {}).text}</Tag></Descriptions.Item>
            <Descriptions.Item label="企业名称" span={2}>{selected.company_name}</Descriptions.Item>
            <Descriptions.Item label="信用代码" span={2}>{selected.unified_social_credit_code}</Descriptions.Item>
            <Descriptions.Item label="营业收入(万元)">{selected.annual_revenue ? Number(selected.annual_revenue).toLocaleString() : '-'}</Descriptions.Item>
            <Descriptions.Item label="利润总额(万元)">{selected.annual_profit ? Number(selected.annual_profit).toLocaleString() : '-'}</Descriptions.Item>
            <Descriptions.Item label="净利润(万元)">{selected.annual_net_profit ? Number(selected.annual_net_profit).toLocaleString() : '-'}</Descriptions.Item>
            <Descriptions.Item label="纳税总额(万元)">{selected.annual_tax_paid ? Number(selected.annual_tax_paid).toLocaleString() : '-'}</Descriptions.Item>
            <Descriptions.Item label="从业人数">{selected.employee_count || '-'}</Descriptions.Item>
            <Descriptions.Item label="经营范围" span={2}>{selected.business_scope || '-'}</Descriptions.Item>
            {selected.submitted_at && <Descriptions.Item label="提交时间" span={2}>{dayjs(selected.submitted_at).format('YYYY-MM-DD HH:mm')}</Descriptions.Item>}
          </Descriptions>
        )}
      </Modal>
    </div>
  )
}

// ===== 公司注册 Tab =====
function RegistrationTab() {
  const [items, setItems] = useState<any[]>([])
  const [createOpen, setCreateOpen] = useState(false)
  const [nameModalOpen, setNameModalOpen] = useState(false)
  const [form] = Form.useForm()
  const [nameForm] = Form.useForm()
  const { currentClientId } = useClient()
  const { message } = App.useApp()
  const [nameSuggestions, setNameSuggestions] = useState<any[]>([])
  const [nameLoading, setNameLoading] = useState(false)
  const [nameIndustry, setNameIndustry] = useState('')

  const fetch = async () => {
    try {
      const res: any = await api.get('/business/registration', { params: { client_id: currentClientId } })
      setItems(res.items || [])
    } catch { /* ignore */ }
  }

  useEffect(() => { fetch() }, [currentClientId])

  const handleCreate = async () => {
    const values = await form.validateFields()
    try {
      await api.post('/business/registration', { ...values, client_id: currentClientId })
      message.success('注册申请已创建')
      setCreateOpen(false); form.resetFields(); fetch()
    } catch (e: any) { message.error(e?.response?.data?.detail || '创建失败') }
  }

  const handleGenerateNames = async () => {
    const vals = await nameForm.validateFields().catch(() => null)
    if (!vals) return
    setNameLoading(true)
    try {
      const res: any = await api.post('/business/name-suggestions', {
        location: vals.location || '',
        industry_keyword: vals.industry || '',
        business_scope: form.getFieldValue('business_scope') || '',
        count: 15,
      })
      setNameSuggestions(res.items || [])
      setNameIndustry(res.industry || '')
    } catch { message.error('起名失败，请重试') }
    finally { setNameLoading(false) }
  }

  const handleUseName = (name: string) => {
    form.setFieldsValue({ company_name: name })
    setNameModalOpen(false)
    message.success(`已选用：${name}`)
  }

  const openNameModal = () => {
    const scope = form.getFieldValue('business_scope') || ''
    const addr = form.getFieldValue('address') || ''
    nameForm.setFieldsValue({ location: addr, industry: '', business_scope: scope })
    setNameModalOpen(true)
  }

  const sourceTag = (source: string) => {
    switch (source) {
      case 'deregistered': return <Tag color="purple" icon={<SafetyCertificateOutlined />}>已注销回收</Tag>
      case 'ai_generated': return <Tag color="blue" icon={<BulbOutlined />}>AI 生成</Tag>
      default: return <Tag>{source}</Tag>
    }
  }

  return (
    <div>
      <Alert
        message="公司注册可通过国家市场监督管理总局官网或各地市场监管局在线办理。本系统记录注册进度，并接入官方页面辅助操作。"
        type="info" showIcon style={{ marginBottom: 16 }}
        action={<Button icon={<GlobalOutlined />} href={OFFICIAL_URLS.registration} target="_blank">前往官方注册</Button>}
      />
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={24}>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>新建注册申请</Button>
          <Button icon={<ThunderboltOutlined />} onClick={async () => {
            const vals = form.getFieldsValue()
            try {
              const res: any = await api.post('/business/auto/generate-form', { task_type: 'registration', data: vals })
              Modal.info({ title: '已生成预填表单', content: `表单「${res.form?.form_name}」已生成，含 ${Object.keys(res.form?.fields || {}).length} 个字段。\n请核对数据后前往官网提交。`, okText: '知道了' })
            } catch (e: any) { Modal.error({ title: '生成失败', content: e?.response?.data?.detail || '请重试' }) }
          }}>生成预填表单</Button>
        </Col>
      </Row>
      <Card title="注册申请记录" size="small">
        {items.length === 0 ? (
          <Empty description="暂无注册申请" />
        ) : (
          items.map((item: any) => (
            <Card key={item.id} size="small" style={{ marginBottom: 8 }}>
              <Descriptions column={4} size="small">
                <Descriptions.Item label="公司名称">{item.detail?.company_name || '-'}</Descriptions.Item>
                <Descriptions.Item label="法人">{item.detail?.legal_person || '-'}</Descriptions.Item>
                <Descriptions.Item label="注册资本">{item.detail?.registered_capital ? `${item.detail.registered_capital}万元` : '-'}</Descriptions.Item>
                <Descriptions.Item label="状态"><Tag>{item.detail?.status || item.action}</Tag></Descriptions.Item>
                <Descriptions.Item label="经营范围" span={2}>{item.detail?.business_scope || '-'}</Descriptions.Item>
                <Descriptions.Item label="操作人">{item.operator}</Descriptions.Item>
                <Descriptions.Item label="时间">{dayjs(item.created_at).format('YYYY-MM-DD HH:mm')}</Descriptions.Item>
              </Descriptions>
            </Card>
          ))
        )}
      </Card>

      {/* 注册申请 Modal */}
      <Modal title="新建公司注册申请" open={createOpen} onOk={handleCreate} onCancel={() => { setCreateOpen(false); form.resetFields() }} width={640}>
        <Form form={form} layout="vertical">
          <Form.Item name="company_name" label="公司名称" rules={[{ required: true }]}>
            <Input
              placeholder="如：XX科技有限公司"
              suffix={<Button size="small" icon={<BulbOutlined />} onClick={openNameModal}>智能起名</Button>}
            />
          </Form.Item>
          <Form.Item name="legal_person" label="法定代表人" rules={[{ required: true }]}>
            <Input placeholder="法人姓名" />
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}><Form.Item name="registered_capital" label="注册资本（万元）"><InputNumber style={{ width: '100%' }} min={0} /></Form.Item></Col>
            <Col span={12}><Form.Item name="contact_phone" label="联系电话"><Input /></Form.Item></Col>
          </Row>
          <Form.Item name="address" label="注册地址"><Input placeholder="公司注册地址" /></Form.Item>
          <Form.Item name="business_scope" label="经营范围"><TextArea rows={3} placeholder="主营业务描述" /></Form.Item>
          <Form.Item name="shareholders" label="股东结构（JSON）"><TextArea rows={2} placeholder='[{"name":"张三","ratio":60,"amount":60}]' /></Form.Item>
        </Form>
      </Modal>

      {/* 智能起名 Modal */}
      <Modal
        title={<span><BulbOutlined style={{ color: '#faad14', marginRight: 8 }} />智能公司起名</span>}
        open={nameModalOpen}
        onCancel={() => setNameModalOpen(false)}
        width={750}
        footer={null}
      >
        <Alert
          message="起名来源：① 回收已注销企业的优质字号 ② AI算法组合吉祥字+行业词生成新字号"
          type="info" showIcon style={{ marginBottom: 16 }}
        />
        <Form form={nameForm} layout="inline" style={{ marginBottom: 16, flexWrap: 'wrap', gap: 8 }}>
          <Form.Item name="location" label="注册地" style={{ flex: '1 1 180px' }}>
            <Input placeholder="如：北京、深圳" />
          </Form.Item>
          <Form.Item name="industry" label="行业" style={{ flex: '1 1 180px' }}>
            <Select
              placeholder="选择行业"
              allowClear
              options={[
                { label: '科技/互联网', value: '科技' }, { label: '贸易/商贸', value: '贸易' },
                { label: '咨询/服务', value: '咨询' }, { label: '餐饮/食品', value: '餐饮' },
                { label: '建筑/工程', value: '建筑' }, { label: '教育/培训', value: '教育' },
                { label: '医疗/健康', value: '医疗' }, { label: '金融/投资', value: '金融' },
                { label: '物流/运输', value: '物流' }, { label: '制造/工业', value: '制造' },
                { label: '电商/零售', value: '电商' }, { label: '新能源/环保', value: '新能源' },
                { label: '文化/传媒', value: '文化' }, { label: '农业/生态', value: '农业' },
              ]}
            />
          </Form.Item>
          <Form.Item style={{ flex: '0 0 auto' }}>
            <Button type="primary" icon={<ThunderboltOutlined />} onClick={handleGenerateNames} loading={nameLoading}>
              生成推荐名称
            </Button>
          </Form.Item>
        </Form>

        {nameSuggestions.length > 0 && (
          <div style={{ maxHeight: 420, overflowY: 'auto' }}>
            <div style={{ marginBottom: 8, color: '#666', fontSize: 13 }}>
              共 <b>{nameSuggestions.length}</b> 个推荐名称，按推荐度排序
            </div>
            {nameSuggestions.map((s: any, idx: number) => (
              <Card
                key={idx}
                size="small"
                style={{ marginBottom: 8 }}
                hoverable
                extra={
                  <Button type="primary" size="small" onClick={() => handleUseName(s.full_name)}>
                    选用
                  </Button>
                }
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
                  <Space size={8}>
                    <Text strong style={{ fontSize: 16 }}>{s.full_name}</Text>
                    {sourceTag(s.source)}
                    <Tag color={s.score >= 85 ? 'gold' : s.score >= 75 ? 'green' : 'default'} icon={<CrownOutlined />}>
                      {s.score}分
                    </Tag>
                  </Space>
                </div>
                <div style={{ marginTop: 4 }}>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    <Text strong>字号：</Text>{s.brand}
                    {s.meaning && <span> — {s.meaning}</span>}
                  </Text>
                </div>
              </Card>
            ))}
          </div>
        )}

        {!nameLoading && nameSuggestions.length === 0 && (
          <Empty description="填写注册地和行业，点击「生成推荐名称」获取智能建议" />
        )}
      </Modal>
    </div>
  )
}

// ===== 公司注销 Tab =====
function DeregistrationTab() {
  const [items, setItems] = useState<any[]>([])
  const [createOpen, setCreateOpen] = useState(false)
  const [form] = Form.useForm()
  const { currentClientId } = useClient()
  const { message } = App.useApp()

  const fetch = async () => {
    try {
      const res: any = await api.get('/business/deregistration', { params: { client_id: currentClientId } })
      setItems(res.items || [])
    } catch { /* ignore */ }
  }
  useEffect(() => { fetch() }, [currentClientId])

  const handleCreate = async () => {
    const values = await form.validateFields()
    try {
      await api.post('/business/deregistration', { ...values, client_id: currentClientId })
      message.success('注销申请已创建')
      setCreateOpen(false); form.resetFields(); fetch()
    } catch (e: any) { message.error(e?.response?.data?.detail || '创建失败') }
  }

  return (
    <div>
      <Alert
        message="公司注销需先完成税务注销，再办理工商注销。注销公告需在国家企业信用信息公示系统公示45天。"
        type="warning" showIcon style={{ marginBottom: 16 }}
        action={<Button icon={<GlobalOutlined />} href={OFFICIAL_URLS.deregistration} target="_blank">官方注销查询</Button>}
      />
      <Space style={{ marginBottom: 16 }}>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>新建注销申请</Button>
        <Button icon={<ThunderboltOutlined />} onClick={async () => {
          const vals = form.getFieldsValue()
          try {
            const res: any = await api.post('/business/auto/generate-form', { task_type: 'deregistration', data: vals })
            Modal.info({ title: '已生成预填表单', content: `表单「${res.form?.form_name}」已生成。\n请核对数据后前往官网提交。`, okText: '知道了' })
          } catch (e: any) { Modal.error({ title: '生成失败', content: e?.response?.data?.detail || '请重试' }) }
        }}>生成预填表单</Button>
      </Space>
      <Card title="注销申请记录" size="small">
        {items.length === 0 ? <Empty description="暂无注销申请" /> : items.map((item: any) => (
          <Card key={item.id} size="small" style={{ marginBottom: 8 }}>
            <Descriptions column={4} size="small">
              <Descriptions.Item label="注销原因">{item.detail?.reason || '-'}</Descriptions.Item>
              <Descriptions.Item label="税务已清">
                <Tag color={item.detail?.tax_cleared ? 'green' : 'red'}>{item.detail?.tax_cleared ? '是' : '否'}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="债务已清">
                <Tag color={item.detail?.debt_cleared ? 'green' : 'red'}>{item.detail?.debt_cleared ? '是' : '否'}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="状态"><Tag>{item.detail?.status || item.action}</Tag></Descriptions.Item>
              <Descriptions.Item label="公告日期">{item.detail?.announcement_date || '-'}</Descriptions.Item>
              <Descriptions.Item label="操作人">{item.operator}</Descriptions.Item>
              <Descriptions.Item label="时间">{dayjs(item.created_at).format('YYYY-MM-DD HH:mm')}</Descriptions.Item>
            </Descriptions>
          </Card>
        ))}
      </Card>
      <Modal title="新建注销申请" open={createOpen} onOk={handleCreate} onCancel={() => { setCreateOpen(false); form.resetFields() }}>
        <Form form={form} layout="vertical">
          <Form.Item name="reason" label="注销原因" rules={[{ required: true }]}><TextArea rows={2} /></Form.Item>
          <Row gutter={16}>
            <Col span={12}><Form.Item name="tax_cleared" label="税务已清算" valuePropName="checked"><Select options={[{ label: '是', value: true }, { label: '否', value: false }]} /></Form.Item></Col>
            <Col span={12}><Form.Item name="debt_cleared" label="债务已清算" valuePropName="checked"><Select options={[{ label: '是', value: true }, { label: '否', value: false }]} /></Form.Item></Col>
          </Row>
          <Form.Item name="announcement_date" label="注销公告日期"><DatePicker style={{ width: '100%' }} /></Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

// ===== 股权变更 Tab =====
function EquityChangeTab() {
  const [items, setItems] = useState<any[]>([])
  const [createOpen, setCreateOpen] = useState(false)
  const [form] = Form.useForm()
  const { currentClientId } = useClient()
  const { message } = App.useApp()

  const fetch = async () => {
    try {
      const res: any = await api.get('/business/equity-change', { params: { client_id: currentClientId } })
      setItems(res.items || [])
    } catch { /* ignore */ }
  }
  useEffect(() => { fetch() }, [currentClientId])

  const handleCreate = async () => {
    const values = await form.validateFields()
    try {
      await api.post('/business/equity-change', { ...values, client_id: currentClientId })
      message.success('股权变更申请已创建')
      setCreateOpen(false); form.resetFields(); fetch()
    } catch (e: any) { message.error(e?.response?.data?.detail || '创建失败') }
  }

  return (
    <div>
      <Alert
        message="股权变更需在市场监督管理局办理变更登记。涉及税务的还需同步办理税务变更。"
        type="info" showIcon style={{ marginBottom: 16 }}
        action={<Button icon={<GlobalOutlined />} href={OFFICIAL_URLS.equity} target="_blank">官方变更查询</Button>}
      />
      <Space style={{ marginBottom: 16 }}>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>新建股权变更</Button>
        <Button icon={<ThunderboltOutlined />} onClick={async () => {
          const vals = form.getFieldsValue()
          try {
            const res: any = await api.post('/business/auto/generate-form', { task_type: 'equity', data: vals })
            Modal.info({ title: '已生成预填表单', content: `表单「${res.form?.form_name}」已生成。\n请核对数据后前往官网提交。`, okText: '知道了' })
          } catch (e: any) { Modal.error({ title: '生成失败', content: e?.response?.data?.detail || '请重试' }) }
        }}>生成预填表单</Button>
      </Space>
      <Card title="股权变更记录" size="small">
        {items.length === 0 ? <Empty description="暂无股权变更记录" /> : items.map((item: any) => (
          <Card key={item.id} size="small" style={{ marginBottom: 8 }}>
            <Descriptions column={4} size="small">
              <Descriptions.Item label="变更类型">
                <Tag color={item.detail?.change_type === 'transfer' ? 'blue' : item.detail?.change_type === 'increase' ? 'green' : 'orange'}>
                  {{transfer: '股权转让', increase: '增资', decrease: '减资'}[item.detail?.change_type] || item.detail?.change_type}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="转出方">{item.detail?.from_person || '-'}</Descriptions.Item>
              <Descriptions.Item label="受让方">{item.detail?.to_person || '-'}</Descriptions.Item>
              <Descriptions.Item label="比例">{item.detail?.ratio ? `${item.detail.ratio}%` : '-'}</Descriptions.Item>
              <Descriptions.Item label="金额">{item.detail?.amount ? `${item.detail.amount}万元` : '-'}</Descriptions.Item>
              <Descriptions.Item label="生效日">{item.detail?.effective_date || '-'}</Descriptions.Item>
              <Descriptions.Item label="状态"><Tag>{item.detail?.status || item.action}</Tag></Descriptions.Item>
              <Descriptions.Item label="操作人">{item.operator}</Descriptions.Item>
            </Descriptions>
          </Card>
        ))}
      </Card>
      <Modal title="新建股权变更" open={createOpen} onOk={handleCreate} onCancel={() => { setCreateOpen(false); form.resetFields() }}>
        <Form form={form} layout="vertical">
          <Form.Item name="change_type" label="变更类型" rules={[{ required: true }]}>
            <Select options={[
              { label: '股权转让', value: 'transfer' },
              { label: '增资', value: 'increase' },
              { label: '减资', value: 'decrease' },
            ]} />
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}><Form.Item name="from_person" label="转出方"><Input /></Form.Item></Col>
            <Col span={12}><Form.Item name="to_person" label="受让方"><Input /></Form.Item></Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}><Form.Item name="ratio" label="变更比例(%)"><InputNumber style={{ width: '100%' }} min={0} max={100} /></Form.Item></Col>
            <Col span={12}><Form.Item name="amount" label="涉及金额(万元)"><InputNumber style={{ width: '100%' }} min={0} /></Form.Item></Col>
          </Row>
          <Form.Item name="effective_date" label="生效日期"><DatePicker style={{ width: '100%' }} /></Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

// ===== 操作日志 Tab =====
function BusinessAuditLogTab() {
  const [logs, setLogs] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [typeFilter, setTypeFilter] = useState<string | undefined>()
  const { currentClientId } = useClient()

  const fetch = async (p = 1) => {
    setLoading(true)
    try {
      const params: any = { page: p, page_size: 30 }
      if (currentClientId) params.client_id = currentClientId
      if (typeFilter) params.target_type = typeFilter
      const res: any = await api.get('/business/audit-log', { params })
      setLogs(res.items || [])
      setTotal(res.total || 0)
      setPage(p)
    } catch { /* ignore */ }
    setLoading(false)
  }

  useEffect(() => { fetch() }, [currentClientId, typeFilter])

  const columns = [
    { title: '操作类型', dataIndex: 'target_type', key: 'type', width: 110,
      render: (v: string) => <Tag>{TYPE_LABELS[v] || v}</Tag> },
    { title: '动作', dataIndex: 'action', key: 'action', width: 80,
      render: (v: string) => <Tag color={v === 'created' ? 'green' : 'blue'}>{v}</Tag> },
    { title: '操作人', dataIndex: 'operator', key: 'operator', width: 100 },
    { title: '详情', dataIndex: 'detail', key: 'detail',
      render: (d: any) => d ? JSON.stringify(d).slice(0, 80) : '-' },
    { title: '时间', dataIndex: 'created_at', key: 'created_at', width: 160,
      render: (v: string) => v ? dayjs(v).format('YYYY-MM-DD HH:mm:ss') : '' },
  ]

  return (
    <div>
      <Alert message="工商中心所有操作（创建/修改/删除年报、注册、注销、股权变更）均完整记录于此，确保合规可追溯。" type="success" showIcon style={{ marginBottom: 16 }} />
      <Space style={{ marginBottom: 16 }}>
        <Select allowClear placeholder="操作类型筛选" style={{ width: 160 }} value={typeFilter} onChange={setTypeFilter}
          options={Object.entries(TYPE_LABELS).map(([k, v]) => ({ label: v, value: k }))} />
        <Button icon={<ReloadOutlined />} onClick={() => fetch()}>刷新</Button>
        <Button icon={<ExportOutlined />} onClick={async () => {
          try {
            const res: any = await auditApi.exportLogs({ target_type: typeFilter })
            const blob = new Blob([res.data || res], { type: 'text/csv' })
            const a = document.createElement('a')
            a.href = URL.createObjectURL(blob)
            a.download = `工商中心操作日志_${dayjs().format('YYYY-MM-DD_HHmmss')}.csv`
            a.click()
          } catch { /* ignore */ }
        }}>导出CSV</Button>
      </Space>
      <Table rowKey="id" columns={columns} dataSource={logs} loading={loading} size="small"
        pagination={{ current: page, total, pageSize: 30, onChange: fetch }} />
    </div>
  )
}


// ===== 企业信息查询 Tab（替代企查查） =====
function CompanyLookupTab() {
  const [keyword, setKeyword] = useState('')
  const [result, setResult] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const { message } = App.useApp()

  const handleSearch = async () => {
    if (!keyword.trim()) return
    setLoading(true)
    setResult(null)
    try {
      const res: any = await api.post('/business/lookup', { keyword: keyword.trim() })
      if (res.success && res.data?.name) {
        setResult(res.data)
        message.success(`查到企业: ${res.data.name}`)
      } else {
        message.warning('未查到该企业信息，请确认名称或税号正确')
      }
    } catch { message.error('查询失败，请稍后重试') }
    setLoading(false)
  }

  return (
    <div>
      <Alert
        message="自动从国家企业信用信息公示系统查询企业工商信息，免费替代企查查/天眼查。输入企业名称或统一社会信用代码即可查询。"
        type="info" showIcon style={{ marginBottom: 16 }}
      />
      <Space.Compact style={{ width: '100%', marginBottom: 24 }}>
        <Input
          size="large"
          placeholder="输入企业名称或统一社会信用代码"
          value={keyword}
          onChange={e => setKeyword(e.target.value)}
          onPressEnter={handleSearch}
          prefix={<SearchOutlined />}
        />
        <Button type="primary" size="large" icon={<ThunderboltOutlined />}
          onClick={handleSearch} loading={loading}>
          查询
        </Button>
        <Button size="large" icon={<GlobalOutlined />}
          onClick={async () => {
            if (!keyword.trim()) return
            setLoading(true); setResult(null)
            try {
              const res: any = await api.post('/business/auto/lookup', { keyword: keyword.trim() })
              if (res.success && res.data?.name) {
                setResult(res.data)
                message.success(`自动查询完成: ${res.data.name} (${res.duration_seconds}s)`)
              } else {
                message.warning(res.message || '未查到')
              }
            } catch { message.error('自动化查询失败') }
            setLoading(false)
          }}>
          自动查询
        </Button>
      </Space.Compact>

      {result && (
        <Card title={<Space><BankOutlined />{result.name}</Space>}
          extra={<Button icon={<GlobalOutlined />} href={result.source_url} target="_blank" size="small">查看官方页面</Button>}
        >
          <Descriptions column={3} bordered size="small">
            <Descriptions.Item label="统一社会信用代码">
              <Space>
                <Text copyable style={{ fontFamily: 'monospace' }}>{result.tax_no || '-'}</Text>
              </Space>
            </Descriptions.Item>
            <Descriptions.Item label="法定代表人">{result.legal_person || '-'}</Descriptions.Item>
            <Descriptions.Item label="经营状态">
              <Tag color={result.business_status?.includes('存续') || result.business_status?.includes('在业') ? 'green' : 'red'}>
                {result.business_status || '-'}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="注册资本">{result.registered_capital || '-'}</Descriptions.Item>
            <Descriptions.Item label="实缴资本">{result.paid_capital || '-'}</Descriptions.Item>
            <Descriptions.Item label="成立日期">{result.established_date || '-'}</Descriptions.Item>
            <Descriptions.Item label="企业类型">{result.company_type || '-'}</Descriptions.Item>
            <Descriptions.Item label="登记机关">{result.registration_authority || '-'}</Descriptions.Item>
            <Descriptions.Item label="所属行业">{result.industry || '-'}</Descriptions.Item>
            <Descriptions.Item label="注册地址" span={3}>{result.address || '-'}</Descriptions.Item>
            <Descriptions.Item label="经营范围" span={3}>
              <Paragraph ellipsis={{ rows: 2, expandable: true }} style={{ margin: 0, fontSize: 12 }}>
                {result.business_scope || '-'}
              </Paragraph>
            </Descriptions.Item>
          </Descriptions>
        </Card>
      )}

      <Card title="查询说明" size="small" style={{ marginTop: 16 }}>
        <ul style={{ margin: 0, paddingLeft: 16, fontSize: 12, color: '#6b7280' }}>
          <li>数据来源：国家企业信用信息公示系统 (gsxt.gov.cn)，权威免费</li>
          <li>支持按企业全称或统一社会信用代码（18位）精确查询</li>
          <li>查询结果可直接用于客户建档，省去手动录入</li>
          <li>无需购买企查查/天眼查等第三方付费服务</li>
        </ul>
      </Card>
    </div>
  )
}


// ===== 工商智能体 Tab =====
function BusinessAgentTab() {
  const [messages, setMessages] = useState<{ role: string; content: string }[]>([
    { role: 'assistant', content: '您好！我是**工商智能体**，专注于公司注册、注销、股权变更、起名、年报等工商业务。请随时提问。' },
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const chatRef = useRef<HTMLDivElement>(null)
  const { message: msgApi } = App.useApp()

  useEffect(() => { chatRef.current?.scrollTo(0, chatRef.current.scrollHeight) }, [messages])

  const handleSend = async () => {
    const txt = input.trim()
    if (!txt || loading) return
    setInput('')
    setMessages(prev => [...prev, { role: 'user', content: txt }])
    setLoading(true)
    try {
      const res: any = await api.post('/business/agent', { message: txt })
      setMessages(prev => [...prev, { role: 'assistant', content: res.reply || '抱歉，暂时无法回复' }])
    } catch {
      msgApi.error('请求失败')
      setMessages(prev => [...prev, { role: 'assistant', content: '抱歉，请求失败，请稍后重试' }])
    }
    setLoading(false)
  }

  const quickQs = [
    '帮我在深圳起一个科技公司名',
    '注册公司需要什么材料？',
    '如何注销公司？',
    '股权转让怎么办理？',
    '查询一下企业信息',
  ]

  return (
    <div>
      <Row gutter={24}>
        <Col xs={24} md={16}>
          <Card
            styles={{ body: { padding: 0 } }}
            title={<span><BulbOutlined style={{ color: '#faad14', marginRight: 8 }} />工商智能体</span>}
          >
            <div ref={chatRef} style={{ height: 420, overflow: 'auto', padding: 16, background: '#f9fafb' }}>
              {messages.map((m, i) => (
                <div key={i} style={{ display: 'flex', gap: 12, marginBottom: 14, flexDirection: m.role === 'user' ? 'row-reverse' : 'row' }}>
                  <div style={{ width: 34, height: 34, borderRadius: '50%', background: m.role === 'user' ? '#1677ff' : '#faad14', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', flexShrink: 0, fontSize: 14 }}>
                    {m.role === 'user' ? <UserOutlined /> : <BulbOutlined />}
                  </div>
                  <div style={{ maxWidth: '75%', padding: '10px 14px', borderRadius: 8, background: m.role === 'user' ? '#1677ff' : '#fff', color: m.role === 'user' ? '#fff' : '#333', boxShadow: '0 1px 3px rgba(0,0,0,0.1)', whiteSpace: 'pre-wrap', lineHeight: 1.8, fontSize: 13 }}>
                    <Text style={{ color: m.role === 'user' ? '#fff' : '#333', fontSize: 13 }}>
                      {m.content.split('**').map((part: string, idx: number) =>
                        idx % 2 === 1 ? <Text key={idx} strong style={{ color: m.role === 'user' ? '#fff' : '#1a1a1a' }}>{part}</Text> : part
                      )}
                    </Text>
                  </div>
                </div>
              ))}
              {loading && <div style={{ textAlign: 'center' }}><Spin /></div>}
            </div>
            <div style={{ padding: '8px 16px', borderTop: '1px solid #f0f0f0', display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {quickQs.map(q => (
                <Tag key={q} color="orange" style={{ cursor: 'pointer', padding: '2px 8px', fontSize: 12 }}
                  onClick={() => setInput(q)}>{q}</Tag>
              ))}
            </div>
            <div style={{ padding: '0 16px 16px', display: 'flex', gap: 8 }}>
              <Input.TextArea
                value={input}
                onChange={e => setInput(e.target.value)}
                onPressEnter={(e: any) => { e.preventDefault(); handleSend() }}
                placeholder="输入工商业务问题，如：帮我在北京起一个贸易公司名..."
                autoSize={{ minRows: 2, maxRows: 4 }}
              />
              <Button type="primary" icon={<SendOutlined />} onClick={handleSend} loading={loading} style={{ alignSelf: 'flex-end' }} />
            </div>
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card size="small" title="💡 使用指南" style={{ marginBottom: 16 }}>
            <ul style={{ margin: 0, paddingLeft: 16, fontSize: 12, color: '#6b7280', lineHeight: 2 }}>
              <li><b>起名</b>：说明城市 + 行业，如「深圳 AI 科技」</li>
              <li><b>注册</b>：问流程、材料、时间、费用</li>
              <li><b>注销</b>：简易注销 vs 一般注销</li>
              <li><b>股权</b>：转让、增资、减资流程</li>
              <li><b>年报</b>：填报时间、内容、逾期后果</li>
              <li><b>查询</b>：企业名称或信用代码查工商信息</li>
            </ul>
          </Card>
          <Card size="small" title="⚡ 快捷入口">
            <Space direction="vertical" style={{ width: '100%' }}>
              <Button block onClick={() => document.querySelector<HTMLElement>('.ant-tabs-tab:first-child')?.click()}>
                <SearchOutlined /> 企业查询
              </Button>
              <Button block onClick={() => {
                const tabs = document.querySelectorAll<HTMLElement>('.ant-tabs-tab')
                if (tabs[2]) tabs[2].click()
              }}><BankOutlined /> 公司注册</Button>
            </Space>
          </Card>
        </Col>
      </Row>
    </div>
  )
}


// ===== 工商中心主页 =====
export default function BusinessCenter() {
  const [activeTab, setActiveTab] = useState('agent')

  return (
    <div style={{ padding: '0 0 24px' }}>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <Title level={3} style={{ margin: 0 }}>
            <BankOutlined style={{ marginRight: 8, color: '#2563eb' }} />
            工商中心
          </Title>
          <Text type="secondary">公司注册 · 注销 · 股权变更 · 年报 — 全生命周期管理 | ⚡ 自动化填报 + 自学习 | 🔍 人工审核最后一步</Text>
        </div>
      </div>
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={[
          { key: 'agent', label: <span><BulbOutlined /> 工商智能体</span>, children: <BusinessAgentTab /> },
          { key: 'lookup', label: <span><SearchOutlined /> 企业查询</span>, children: <CompanyLookupTab /> },
          { key: 'annual', label: <span><FileProtectOutlined /> 工商年报</span>, children: <AnnualReportTab /> },
          { key: 'registration', label: <span><BankOutlined /> 公司注册</span>, children: <RegistrationTab /> },
          { key: 'deregistration', label: <span><CloseCircleOutlined /> 公司注销</span>, children: <DeregistrationTab /> },
          { key: 'equity', label: <span><SwapOutlined /> 股权变更</span>, children: <EquityChangeTab /> },
          { key: 'audit', label: <span><AuditOutlined /> 操作日志</span>, children: <BusinessAuditLogTab /> },
        ]}
      />
    </div>
  )
}
