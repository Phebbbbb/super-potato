import { useState } from 'react'
import { Card, Button, Space, App, Typography, Form, Input, Table, Tag, Descriptions, Upload, Result, Spin } from 'antd'
import { SafetyOutlined, InboxOutlined, UploadOutlined } from '@ant-design/icons'
import { verifyApi } from '@/services/api'
import { useClient } from '@/contexts/ClientContext'

const { Text } = Typography

export default function InvoiceVerify() {
  const { message } = App.useApp()
  const [mode, setMode] = useState<'single' | 'batch'>('single')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<any>(null)
  const [batchResults, setBatchResults] = useState<any[]>([])
  const [form] = Form.useForm()

  const handleSingle = async () => {
    const values = await form.validateFields()
    setLoading(true)
    try {
      const res: any = await verifyApi.verify(values)
      setResult(res)
      if (res.is_valid) message.success('发票为真，查验通过')
      else message.warning(res.message || '查验结果异常')
    } catch { message.error('查验失败') }
    setLoading(false)
  }

  const handleBatchFile = async (file: File) => {
    setLoading(true)
    try {
      const text = await file.text()
      const lines = text.split('\n').filter(l => l.trim())
      // Parse CSV: invoice_code,invoice_no,invoice_date,amount,check_code
      const invoices = lines.slice(1).map(line => {
        const [invoice_code, invoice_no, invoice_date, amount, check_code] = line.split(',').map(s => (s || '').trim())
        return { invoice_code, invoice_no, invoice_date, amount, check_code }
      }).filter(r => r.invoice_code && r.invoice_no)

      if (invoices.length === 0) { message.warning('未能解析到发票信息'); setLoading(false); return false }
      const res: any = await verifyApi.verifyBatch({ invoices })
      setBatchResults(res.results || [])
      message.success(`批量查验完成：${res.valid} 真，${res.invalid} 假，${res.failed} 失败`)
    } catch { message.error('批量查验失败') }
    setLoading(false)
    return false
  }

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h2 style={{ margin: 0 }}>发票真伪查验</h2>
        <Text type="secondary">对接全国增值税发票查验平台，支持单张/批量查验</Text>
      </div>

      <Card style={{ marginBottom: 16 }}>
        <Space>
          <Button type={mode === 'single' ? 'primary' : 'default'} onClick={() => { setMode('single'); setResult(null) }}>
            单张查验
          </Button>
          <Button type={mode === 'batch' ? 'primary' : 'default'} onClick={() => { setMode('batch'); setBatchResults([]) }}>
            批量查验
          </Button>
        </Space>
      </Card>

      {mode === 'single' && (
        <Card title="单张发票查验">
          <Form form={form} layout="vertical" style={{ maxWidth: 500 }}>
            <Form.Item name="invoice_code" label="发票代码" rules={[{ required: true, message: '请输入发票代码（10或12位）' }]}>
              <Input placeholder="请输入发票代码" maxLength={12} />
            </Form.Item>
            <Form.Item name="invoice_no" label="发票号码" rules={[{ required: true, message: '请输入发票号码（8位）' }]}>
              <Input placeholder="请输入发票号码" maxLength={8} />
            </Form.Item>
            <Form.Item name="invoice_date" label="开票日期" rules={[{ required: true, message: '请选择开票日期' }]}>
              <Input placeholder="YYYY-MM-DD" />
            </Form.Item>
            <Form.Item name="amount" label="开具金额（不含税）">
              <Input placeholder="选填" />
            </Form.Item>
            <Form.Item name="check_code" label="校验码后6位">
              <Input placeholder="选填" maxLength={6} />
            </Form.Item>
            <Button type="primary" icon={<SafetyOutlined />} loading={loading} onClick={handleSingle}>
              开始查验
            </Button>
          </Form>
        </Card>
      )}

      {mode === 'batch' && (
        <Card title="批量发票查验">
          <div style={{ marginBottom: 16, padding: 12, background: '#fafafa', borderRadius: 6 }}>
            <Text type="secondary">上传 CSV 文件，格式：发票代码,发票号码,开票日期,金额,校验码（一行一张，首行为标题）</Text>
          </div>
          <Upload beforeUpload={handleBatchFile} showUploadList={false} accept=".csv">
            <Button type="primary" icon={<UploadOutlined />} loading={loading}>上传 CSV 批量查验</Button>
          </Upload>
        </Card>
      )}

      {loading && <Spin style={{ display: 'block', margin: '24px auto' }} />}

      {result && mode === 'single' && (
        <Card title="查验结果" style={{ marginTop: 16 }}>
          <Result
            status={result.is_valid ? 'success' : 'warning'}
            title={result.is_valid ? '发票查验通过' : result.message || '查验未通过'}
          />
          {result.details && (
            <Descriptions column={2} bordered size="small" style={{ marginTop: 16 }}>
              <Descriptions.Item label="发票类型">{result.details.invoice_type || '-'}</Descriptions.Item>
              <Descriptions.Item label="销方名称">{result.details.seller_name || '-'}</Descriptions.Item>
              <Descriptions.Item label="购方名称">{result.details.buyer_name || '-'}</Descriptions.Item>
              <Descriptions.Item label="开票日期">{result.details.invoice_date || '-'}</Descriptions.Item>
              <Descriptions.Item label="合计金额">¥{result.details.total_amount || '-'}</Descriptions.Item>
              <Descriptions.Item label="税额">¥{result.details.tax_amount || '-'}</Descriptions.Item>
              <Descriptions.Item label="价税合计">¥{result.details.grand_total || '-'}</Descriptions.Item>
              <Descriptions.Item label="查验次数">{result.details.verify_count || '-'}</Descriptions.Item>
            </Descriptions>
          )}
        </Card>
      )}

      {batchResults.length > 0 && (
        <Card title={`批量查验结果 — ${batchResults.length} 张`} style={{ marginTop: 16 }}>
          <Table dataSource={batchResults} rowKey={(r: any) => `${r.invoice_code}-${r.invoice_no}`} size="small" pagination={false}
            columns={[
              { title: '发票代码', dataIndex: 'invoice_code', width: 130 },
              { title: '发票号码', dataIndex: 'invoice_no', width: 100 },
              { title: '查验结果', dataIndex: 'is_valid', width: 100,
                render: (v: boolean) => <Tag color={v ? 'green' : 'red'}>{v ? '真票' : '假票'}</Tag> },
              { title: '说明', dataIndex: 'message', ellipsis: true },
              { title: '销方', dataIndex: ['details', 'seller_name'], width: 150, ellipsis: true },
              { title: '金额', dataIndex: ['details', 'grand_total'], width: 100,
                render: (v: string) => v ? `¥${Number(v).toLocaleString()}` : '-' },
            ]} />
        </Card>
      )}
    </div>
  )
}
