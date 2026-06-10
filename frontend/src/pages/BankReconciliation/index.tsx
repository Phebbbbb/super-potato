import { useState, useEffect } from 'react'
import { Card, Table, Button, Space, Modal, Form, Input, Select, DatePicker, App, Tag, Statistic, Row, Col, Upload } from 'antd'
import { PlusOutlined, UploadOutlined, ApiOutlined, LinkOutlined, ReloadOutlined, InboxOutlined, FileTextOutlined } from '@ant-design/icons'
import { bankApi } from '@/services/api'
import { useClient } from '@/contexts/ClientContext'
import dayjs from 'dayjs'
import SkeletonTable from '@/components/SkeletonTable'
import EmptyState from '@/components/EmptyState'

export default function BankReconciliation() {
  const [accounts, setAccounts] = useState<any[]>([])
  const [statements, setStatements] = useState<any[]>([])
  const [summary, setSummary] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [accOpen, setAccOpen] = useState(false)
  const [selectedAccount, setSelectedAccount] = useState<string>('')
  const [accForm] = Form.useForm()
  const { currentClientId } = useClient()
  const { message } = App.useApp()
  const [autoVoucherPeriod, setAutoVoucherPeriod] = useState(dayjs().format('YYYY-MM'))
  const [autoVoucherLoading, setAutoVoucherLoading] = useState(false)

  const fetchData = async () => {
    if (!currentClientId) return
    setLoading(true)
    try {
      const res: any = await bankApi.listAccounts({ client_id: currentClientId })
      setAccounts(res.items || [])
      if (res.items?.[0]) {
        setSelectedAccount(res.items[0].id)
        await loadStatements(res.items[0].id)
      }
    } catch { message.error('加载数据失败') }
    setLoading(false)
  }

  useEffect(() => { fetchData() }, [currentClientId])

  const loadStatements = async (accountId: string) => {
    try {
      const [sRes, sumRes]: any[] = await Promise.all([
        bankApi.listStatements({ bank_account_id: accountId, page_size: 200 }),
        bankApi.reconciliation(accountId),
      ])
      setStatements(sRes.items || [])
      setSummary(sumRes)
    } catch { message.error('加载数据失败') }
  }

  const handleAddAccount = async () => {
    const values = await accForm.validateFields()
    await bankApi.createAccount({ ...values, client_id: currentClientId })
    message.success('银行账户添加成功')
    setAccOpen(false); accForm.resetFields(); fetchData()
  }

  const handleImport = async (file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    try {
      const data: any = await bankApi.importStatements(selectedAccount, currentClientId, formData)
      message.success(`导入成功：${data.imported} 条流水`)
      loadStatements(selectedAccount)
    } catch { message.error('导入失败') }
    return false
  }

  const handleAutoMatch = async () => {
    try {
      const res: any = await bankApi.autoMatch(selectedAccount)
      message.success(`自动匹配完成：${res.matched_count} 条`)
      loadStatements(selectedAccount)
    } catch { message.error('匹配失败') }
  }

  const handleAutoGenerateVouchers = async () => {
    if (!selectedAccount) { message.warning('请先选择银行账户'); return }
    setAutoVoucherLoading(true)
    try {
      const res: any = await bankApi.autoGenerateVouchers(selectedAccount, autoVoucherPeriod)
      message.success(res.message || `已生成 ${res.vouchers_created} 张凭证`)
      loadStatements(selectedAccount)
    } catch { message.error('生成凭证失败') }
    setAutoVoucherLoading(false)
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 24 }}>
        <h2>银企对账</h2>
        <Space>
          <Select value={selectedAccount} onChange={(v: string) => { setSelectedAccount(v); loadStatements(v) }}
            style={{ width: 250 }} placeholder="选择银行账户" options={accounts.map(a => ({ label: `${a.bank_name} - ${a.account_no}`, value: a.id }))} />
          <Button icon={<PlusOutlined />} onClick={() => setAccOpen(true)}>添加账户</Button>
        </Space>
      </div>

      {summary && (
        <Row gutter={16} style={{ marginBottom: 24 }}>
          <Col span={6}><Card><Statistic title="流水总数" value={summary.total_lines} /></Card></Col>
          <Col span={6}><Card><Statistic title="已匹配" value={summary.matched_count} valueStyle={{ color: 'green' }} /></Card></Col>
          <Col span={6}><Card><Statistic title="未匹配" value={summary.unmatched_count} valueStyle={{ color: 'red' }} /></Card></Col>
          <Col span={6}><Card><Statistic title="匹配率" value={summary.total_lines > 0 ? `${Math.round(summary.matched_count / summary.total_lines * 100)}%` : '0%'} /></Card></Col>
        </Row>
      )}

      <Card title="银行流水" style={{ flex: 1, overflow: 'auto', minHeight: 0 }}
        extra={
          <Space>
            <Upload beforeUpload={handleImport} showUploadList={false}><Button icon={<UploadOutlined />}>导入CSV</Button></Upload>
            <Button icon={<ApiOutlined />} onClick={handleAutoMatch}>自动匹配</Button>
            <DatePicker picker="month" value={dayjs(autoVoucherPeriod, 'YYYY-MM')} onChange={(d) => d && setAutoVoucherPeriod(d.format('YYYY-MM'))} style={{ width: 120 }} size="small" />
            <Button icon={<FileTextOutlined />} loading={autoVoucherLoading} onClick={handleAutoGenerateVouchers}>生成凭证</Button>
            <Button icon={<ReloadOutlined />} onClick={() => loadStatements(selectedAccount)}>刷新</Button>
          </Space>
        }>
        <Table dataSource={statements} rowKey="id" size="small" loading={loading} pagination={false}
          locale={{ emptyText: '暂无流水，请先导入银行对账单 CSV 文件' }}
          columns={[
            { title: '日期', dataIndex: 'transaction_date', width: 110 },
            { title: '摘要', dataIndex: 'description', width: 200 },
            { title: '借方(支出)', dataIndex: 'debit', width: 130, render: (v: number) => v ? `¥${v.toLocaleString()}` : '-' },
            { title: '贷方(收入)', dataIndex: 'credit', width: 130, render: (v: number) => v ? `¥${v.toLocaleString()}` : '-' },
            { title: '余额', dataIndex: 'balance', width: 130, render: (v: number) => `¥${v?.toLocaleString()}` },
            { title: '对方', dataIndex: 'counterparty', width: 120 },
            { title: '匹配状态', dataIndex: 'match_status', width: 100,
              render: (s: string) => {
                const m: Record<string, { color: string; text: string }> = { unmatched: { color: 'red', text: '未匹配' }, auto_matched: { color: 'green', text: '自动匹配' }, manual_matched: { color: 'blue', text: '手动匹配' }, ignored: { color: 'default', text: '忽略' } }
                return <Tag color={m[s]?.color}>{m[s]?.text || s}</Tag>
              }},
          ]}
        />
      </Card>

      <Modal title="添加银行账户" open={accOpen} onOk={handleAddAccount} onCancel={() => setAccOpen(false)}>
        <Form form={accForm} layout="vertical">
          <Form.Item label="银行名称" name="bank_name" rules={[{ required: true }]}><Input placeholder="如：中国工商银行" /></Form.Item>
          <Form.Item label="账号" name="account_no" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item label="账户名称" name="account_name" rules={[{ required: true }]}><Input /></Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
