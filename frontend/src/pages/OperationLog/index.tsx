import { useState, useEffect } from 'react'
import { Table, Select, Button, Space, App, Tag, Typography, DatePicker } from 'antd'
import { SearchOutlined, ReloadOutlined, DownloadOutlined, ClearOutlined } from '@ant-design/icons'
import { auditApi } from '@/services/api'
import dayjs from 'dayjs'

const { Text } = Typography
const { RangePicker } = DatePicker

export default function OperationLog() {
  const { message } = App.useApp()
  const [logs, setLogs] = useState<any[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [filters, setFilters] = useState<{ action?: string; target_type?: string; date_from?: string; date_to?: string }>({})

  const loadLogs = async (p = 1, f: any = filters) => {
    setLoading(true)
    try {
      const params: any = { page: p, page_size: 50, ...f }
      const res: any = await auditApi.logs(params)
      setLogs(res.items || [])
      setTotal(res.total || 0)
      setPage(p)
    } catch { message.error('加载操作日志失败') }
    setLoading(false)
  }

  const handleExport = async () => {
    try {
      const res: any = await auditApi.exportLogs(filters)
      const url = window.URL.createObjectURL(new Blob([res.data || res]))
      const a = document.createElement('a')
      a.href = url
      a.download = `操作日志_${dayjs().format('YYYY-MM-DD_HHmmss')}.csv`
      a.click()
      window.URL.revokeObjectURL(url)
      message.success('导出成功')
    } catch { message.error('导出失败') }
  }

  const handleFilterChange = (key: string, value: any) => {
    const next = { ...filters, [key]: value || undefined }
    if (!value) delete next[key as keyof typeof next]
    setFilters(next)
  }

  useEffect(() => { loadLogs() }, [])

  return (
    <div>
      <h2 style={{ marginBottom: 16 }}>操作日志</h2>

      <Space wrap style={{ marginBottom: 12 }}>
        <Select
          allowClear placeholder="操作类型" style={{ width: 120 }}
          value={filters.action}
          onChange={v => handleFilterChange('action', v)}
          options={[
            { label: '创建', value: 'created' }, { label: '修改', value: 'updated' },
            { label: '删除', value: 'deleted' }, { label: '确认', value: 'confirmed' },
            { label: '回滚', value: 'reverted' }, { label: '状态变更', value: 'status_change' },
            { label: '登录', value: 'login' },
          ]}
        />
        <Select
          allowClear placeholder="对象类型" style={{ width: 130 }}
          value={filters.target_type}
          onChange={v => handleFilterChange('target_type', v)}
          options={[
            { label: '凭证', value: 'voucher' }, { label: '发票', value: 'invoice' },
            { label: '申报', value: 'filing' }, { label: '票据', value: 'document' },
            { label: '客户', value: 'client' }, { label: '员工', value: 'employee' },
            { label: '用户', value: 'user' }, { label: '工资', value: 'payroll' },
            { label: '科目', value: 'account' }, { label: '银行流水', value: 'bank_statement' },
            { label: '系统配置', value: 'system_config' }, { label: '外勤任务', value: 'field_task' },
          ]}
        />
        <RangePicker
          onChange={(_, [from, to]) => {
            handleFilterChange('date_from', from || undefined)
            handleFilterChange('date_to', to || undefined)
          }}
        />
        <Button icon={<SearchOutlined />} onClick={() => loadLogs(1)}>筛选</Button>
        <Button icon={<ClearOutlined />} onClick={() => { setFilters({}); loadLogs(1, {}); }}>重置</Button>
        <Button icon={<DownloadOutlined />} onClick={handleExport}>导出CSV</Button>
        <Button icon={<ReloadOutlined />} onClick={() => loadLogs()} loading={loading} />
      </Space>

      <Table
        dataSource={logs}
        rowKey="id"
        size="small"
        loading={loading}
        locale={{ emptyText: '暂无操作记录，系统操作后将自动记录' }}
        pagination={{
          current: page,
          pageSize: 50,
          total,
          showTotal: t => `共 ${t} 条`,
          onChange: p => loadLogs(p),
        }}
        columns={[
          { title: '时间', dataIndex: 'created_at', width: 170, render: (v: string) => v ? dayjs(v).format('YYYY-MM-DD HH:mm:ss') : '-' },
          { title: '操作人', dataIndex: 'operator', width: 120 },
          {
            title: '操作', dataIndex: 'action', width: 100,
            render: (v: string) => {
              const m: Record<string, { color: string; text: string }> = {
                created: { color: 'green', text: '创建' }, updated: { color: 'blue', text: '修改' },
                deleted: { color: 'red', text: '删除' }, confirmed: { color: 'cyan', text: '确认' },
                reverted: { color: 'orange', text: '回滚' }, status_change: { color: 'purple', text: '状态变更' },
                approved: { color: 'green', text: '通过' }, rejected: { color: 'red', text: '驳回' },
                login: { color: 'geekblue', text: '登录' },
              }
              return <Tag color={m[v]?.color || 'default'}>{m[v]?.text || v}</Tag>
            },
          },
          { title: '对象类型', dataIndex: 'target_type', width: 100, render: (v: string) => {
            const t: Record<string, string> = {
              voucher: '凭证', invoice: '发票', filing: '申报', document: '票据', client: '客户',
              employee: '员工', user: '用户', payroll: '工资', account: '科目',
              bank_statement: '银行流水', system_config: '系统配置', field_task: '外勤任务',
              bank_account: '银行账户', payroll_batch: '工资批次', payroll_detail: '工资明细',
            }
            return t[v] || v
          }},
          { title: '对象ID', dataIndex: 'target_id', width: 90, render: (v: string) => <Text code style={{ fontSize: 11 }}>{v?.slice(0, 8)}</Text> },
          { title: '详情', dataIndex: 'detail', ellipsis: true, render: (v: string) => v ? <Text type="secondary" style={{ fontSize: 11, maxWidth: 200 }} ellipsis>{v}</Text> : '-' },
        ]}
      />
    </div>
  )
}
