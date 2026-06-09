import { useState, useEffect } from 'react'
import { Card, Table, Button, Space, Tag, Modal, Form, Input, Select, InputNumber, DatePicker, App, Row, Col, Statistic, Typography, Descriptions } from 'antd'
import { PlusOutlined, EditOutlined, DeleteOutlined, FileProtectOutlined, WarningOutlined, CheckCircleOutlined, EyeOutlined } from '@ant-design/icons'
import { useClient } from '@/contexts/ClientContext'
import api from '@/services/api'
import dayjs from 'dayjs'

const { Text } = Typography

export default function AnnualReports() {
  const [reports, setReports] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [detailOpen, setDetailOpen] = useState(false)
  const [selected, setSelected] = useState<any>(null)
  const [missingYears, setMissingYears] = useState<number[]>([])
  const [form] = Form.useForm()
  const { currentClientId } = useClient()
  const { message } = App.useApp()

  const fetchReports = async () => {
    if (!currentClientId) return
    setLoading(true)
    try {
      const res: any = await api.get('/annual-reports/', { params: { client_id: currentClientId } })
      setReports(res.items || [])
      setMissingYears(res.missing_years || [])
    } catch { message.error('加载年报列表失败') }
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

  const handleDelete = async (record: any) => {
    Modal.confirm({
      title: '确认删除', content: `删除 ${record.report_year} 年度年报?`,
      onOk: async () => {
        try { await api.delete(`/annual-reports/${record.id}`); message.success('已删除'); fetchReports() }
        catch { message.error('删除失败') }
      },
    })
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
      title: '确认提交', content: `提交 ${record.report_year} 年度年报至市场监督管理局？提交后将不可撤回。`,
      onOk: async () => {
        try {
          await api.patch(`/annual-reports/${record.id}`, { status: 'submitted', operator: '当前用户' })
          message.success('年报已提交'); fetchReports()
        } catch { message.error('提交失败') }
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
    { title: '营业收入', dataIndex: 'annual_revenue', width: 120, align: 'right' as const, render: (v: string) => v ? `¥${Number(v).toLocaleString()}` : '-' },
    { title: '从业人数', dataIndex: 'employee_count', width: 80, align: 'right' as const },
    {
      title: '状态', dataIndex: 'status', width: 90,
      render: (s: string) => <Tag color={(statusMap[s] || {}).color}>{(statusMap[s] || {}).text || s}</Tag>,
    },
    { title: '提交时间', dataIndex: 'submitted_at', width: 110, render: (v: string) => v ? dayjs(v).format('YYYY-MM-DD') : '-' },
    {
      title: '操作', width: 220,
      render: (_: any, r: any) => (
        <Space size={0}>
          <Button type="link" size="small" icon={<EyeOutlined />} onClick={() => handleView(r)}>查看</Button>
          {r.status === 'draft' && (
            <>
              <Button type="link" size="small" icon={<CheckCircleOutlined />} onClick={() => handleSubmit(r)} style={{ color: '#16a34a' }}>提交</Button>
              <Button type="link" size="small" danger icon={<DeleteOutlined />} onClick={() => handleDelete(r)}>删除</Button>
            </>
          )}
        </Space>
      ),
    },
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 24 }}>
        <h2><FileProtectOutlined /> 工商年报</h2>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => { form.resetFields(); setCreateOpen(true) }}>
          新建年报
        </Button>
      </div>

      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card size="small"><Statistic title="年报总数" value={reports.length} suffix="份" /></Card>
        </Col>
        <Col span={6}>
          <Card size="small"><Statistic title="已提交/公示" value={submittedCount} suffix="份" valueStyle={{ color: '#16a34a' }} /></Card>
        </Col>
        <Col span={6}>
          <Card size="small"><Statistic title="草稿" value={reports.filter(r => r.status === 'draft').length} suffix="份" valueStyle={{ color: '#d97706' }} /></Card>
        </Col>
        <Col span={6}>
          <Card size="small" style={{ borderColor: missingYears.length > 0 ? '#dc2626' : undefined }}>
            <Statistic
              title={<Space><WarningOutlined style={{ color: missingYears.length > 0 ? '#dc2626' : '#94a3b8' }} />缺失年度</Space>}
              value={missingYears.length} suffix="个"
              valueStyle={{ color: missingYears.length > 0 ? '#dc2626' : '#64748b' }}
            />
            {missingYears.length > 0 && (
              <Text type="danger" style={{ fontSize: 11 }}>缺失: {missingYears.join(', ')}年度 — 请尽快补报</Text>
            )}
          </Card>
        </Col>
      </Row>

      {missingYears.length > 0 && (
        <Card size="small" style={{ marginBottom: 16, background: '#fef2f2', borderColor: '#fecaca' }}>
          <Space>
            <WarningOutlined style={{ color: '#dc2626' }} />
            <Text style={{ color: '#dc2626' }}>
              以下年度工商年报缺失：{missingYears.join('、')}。根据《企业信息公示暂行条例》，企业应于每年1月1日至6月30日报送上一年度年报，逾期将被列入经营异常名录。
            </Text>
          </Space>
        </Card>
      )}

      <Card>
        <Table dataSource={reports} columns={columns} rowKey="id" loading={loading} pagination={false} />
      </Card>

      {/* 新建年报 Modal */}
      <Modal title="新建工商年报" open={createOpen} onOk={handleCreate} onCancel={() => setCreateOpen(false)} width={700}>
        <Form form={form} layout="vertical" initialValues={{ report_year: currentYear - 1, is_listed: '否', has_party_org: '否' }}>
          <Space size={12}>
            <Form.Item label="报告年度" name="report_year" rules={[{ required: true }]}>
              <Select style={{ width: 120 }} options={[currentYear - 1, currentYear - 2].map(y => ({ label: `${y}年度`, value: y }))} />
            </Form.Item>
            <Form.Item label="企业名称" name="company_name" rules={[{ required: true }]}>
              <Input style={{ width: 240 }} />
            </Form.Item>
            <Form.Item label="统一社会信用代码" name="unified_social_credit_code" rules={[{ required: true }]}>
              <Input style={{ width: 200 }} />
            </Form.Item>
          </Space>
          <Space size={12}>
            <Form.Item label="法人代表" name="legal_representative"><Input style={{ width: 140 }} /></Form.Item>
            <Form.Item label="联系电话" name="contact_phone"><Input style={{ width: 140 }} /></Form.Item>
            <Form.Item label="从业人数" name="employee_count"><InputNumber style={{ width: 100 }} /></Form.Item>
          </Space>
          <Space size={12}>
            <Form.Item label="资产总额(万元)" name="total_assets"><InputNumber style={{ width: 140 }} /></Form.Item>
            <Form.Item label="负债总额(万元)" name="total_liabilities"><InputNumber style={{ width: 140 }} /></Form.Item>
            <Form.Item label="营业收入(万元)" name="annual_revenue"><InputNumber style={{ width: 140 }} /></Form.Item>
            <Form.Item label="利润总额(万元)" name="annual_profit"><InputNumber style={{ width: 140 }} /></Form.Item>
          </Space>
          <Space size={12}>
            <Form.Item label="净利润(万元)" name="annual_net_profit"><InputNumber style={{ width: 140 }} /></Form.Item>
            <Form.Item label="纳税总额(万元)" name="annual_tax_paid"><InputNumber style={{ width: 140 }} /></Form.Item>
            <Form.Item label="参保人数" name="social_insurance_participants"><InputNumber style={{ width: 100 }} /></Form.Item>
          </Space>
          <Form.Item label="经营范围" name="business_scope"><Input.TextArea rows={2} /></Form.Item>
        </Form>
      </Modal>

      {/* 年报详情 Modal */}
      <Modal title={`${selected?.report_year}年度 工商年报详情`} open={detailOpen} onCancel={() => setDetailOpen(false)} footer={<Button onClick={() => setDetailOpen(false)}>关闭</Button>} width={800}>
        {selected && (
          <Descriptions bordered size="small" column={2}>
            <Descriptions.Item label="报告年度">{selected.report_year}</Descriptions.Item>
            <Descriptions.Item label="状态"><Tag color={(statusMap[selected.status] || {}).color}>{(statusMap[selected.status] || {}).text}</Tag></Descriptions.Item>
            <Descriptions.Item label="企业名称" span={2}>{selected.company_name}</Descriptions.Item>
            <Descriptions.Item label="信用代码" span={2}>{selected.unified_social_credit_code}</Descriptions.Item>
            <Descriptions.Item label="法人代表">{selected.legal_representative || '-'}</Descriptions.Item>
            <Descriptions.Item label="联系电话">{selected.contact_phone || '-'}</Descriptions.Item>
            <Descriptions.Item label="从业人数">{selected.employee_count || '-'}</Descriptions.Item>
            <Descriptions.Item label="是否上市">{selected.is_listed || '否'}</Descriptions.Item>
            <Descriptions.Item label="资产总额">{selected.total_assets ? `¥${Number(selected.total_assets).toLocaleString()}` : '-'}</Descriptions.Item>
            <Descriptions.Item label="负债总额">{selected.total_liabilities ? `¥${Number(selected.total_liabilities).toLocaleString()}` : '-'}</Descriptions.Item>
            <Descriptions.Item label="营业收入">{selected.annual_revenue ? `¥${Number(selected.annual_revenue).toLocaleString()}` : '-'}</Descriptions.Item>
            <Descriptions.Item label="利润总额">{selected.annual_profit ? `¥${Number(selected.annual_profit).toLocaleString()}` : '-'}</Descriptions.Item>
            <Descriptions.Item label="净利润">{selected.annual_net_profit ? `¥${Number(selected.annual_net_profit).toLocaleString()}` : '-'}</Descriptions.Item>
            <Descriptions.Item label="纳税总额">{selected.annual_tax_paid ? `¥${Number(selected.annual_tax_paid).toLocaleString()}` : '-'}</Descriptions.Item>
            <Descriptions.Item label="参保人数">{selected.social_insurance_participants || '-'}</Descriptions.Item>
            <Descriptions.Item label="社保缴费基数">{selected.social_insurance_base || '-'}</Descriptions.Item>
            <Descriptions.Item label="实际缴费金额">{selected.social_insurance_paid || '-'}</Descriptions.Item>
            <Descriptions.Item label="欠缴金额">{selected.social_insurance_arrears || '-'}</Descriptions.Item>
            <Descriptions.Item label="经营范围" span={2}>{selected.business_scope || '-'}</Descriptions.Item>
            {selected.submitted_at && <Descriptions.Item label="提交时间" span={2}>{dayjs(selected.submitted_at).format('YYYY-MM-DD HH:mm')}</Descriptions.Item>}
            {selected.samr_receipt_no && <Descriptions.Item label="回执编号" span={2}>{selected.samr_receipt_no}</Descriptions.Item>}
          </Descriptions>
        )}
      </Modal>
    </div>
  )
}
