import { useState, useEffect, useCallback } from 'react'
import { Card, Tabs, Table, Select, Button, Space, App, Spin } from 'antd'
import { DownloadOutlined } from '@ant-design/icons'
import { reportApi } from '@/services/api'

function generatePeriods() {
  const now = new Date()
  const periods: string[] = []
  for (let i = 0; i < 12; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1)
    periods.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`)
  }
  return periods
}
const PERIODS = generatePeriods()

export default function Reports() {
  const [period, setPeriod] = useState('2026-06')
  const [loading, setLoading] = useState(false)
  const [trialBalance, setTrialBalance] = useState<any[]>([])
  const [incomeStatement, setIncomeStatement] = useState<any>(null)
  const [balanceSheet, setBalanceSheet] = useState<any>(null)
  const [generalLedger, setGeneralLedger] = useState<any[]>([])
  const [cashFlow, setCashFlow] = useState<any>(null)
  const { message } = App.useApp()

  const fetchAll = useCallback(async () => {
    setLoading(true)
    try {
      const [tb, inc, bs, gl, cf] = await Promise.all([
        reportApi.trialBalance(period),
        reportApi.incomeStatement(period),
        reportApi.balanceSheet(period),
        reportApi.generalLedger(period),
        reportApi.cashFlow(period),
      ])
      setTrialBalance((tb as any)?.items || tb || [])
      setIncomeStatement(inc)
      setBalanceSheet(bs)
      setGeneralLedger((gl as any)?.items || gl || [])
      setCashFlow(cf)
    } catch { message.error('加载报表失败') }
    setLoading(false)
  }, [period])

  useEffect(() => { fetchAll() }, [fetchAll])

  const handleExport = async (reportType: string) => {
    try {
      const data: any = await reportApi.export(reportType, period)
      // Generate CSV from report data
      let csv = '﻿' // BOM for Excel UTF-8
      const items = Array.isArray(data) ? data : (data?.items || [])
      if (items.length > 0) {
        const headers = Object.keys(items[0])
        csv += headers.join(',') + '\n'
        items.forEach((row: any) => {
          csv += headers.map(h => {
            const v = row[h]
            if (v == null || v === '') return ''
            const s = String(v).replace(/"/g, '""')
            return s.includes(',') || s.includes('\n') ? `"${s}"` : s
          }).join(',') + '\n'
        })
      }
      const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = `${reportType}_${period}.csv`; a.click()
      URL.revokeObjectURL(url)
      message.success('导出成功')
    } catch { message.error('导出失败') }
  }

  const amountRender = (v: any) => v != null ? `¥${Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 2 })}` : '-'

  const tabItems = [
    {
      key: 'trial-balance', label: '科目余额表',
      children: (
        <Table dataSource={Array.isArray(trialBalance) ? trialBalance : []} rowKey="account_code" size="small" loading={loading}
          locale={{ emptyText: '暂无数据' }} scroll={{ x: 1100 }}
          columns={[
            { title: '科目编码', dataIndex: 'account_code', width: 100 },
            { title: '科目名称', dataIndex: 'account_name', width: 180 },
            { title: '期初借方', dataIndex: 'opening_debit', width: 140, render: amountRender },
            { title: '期初贷方', dataIndex: 'opening_credit', width: 140, render: amountRender },
            { title: '本期借方', dataIndex: 'period_debit', width: 140, render: amountRender },
            { title: '本期贷方', dataIndex: 'period_credit', width: 140, render: amountRender },
            { title: '期末借方', dataIndex: 'closing_debit', width: 140, render: amountRender },
            { title: '期末贷方', dataIndex: 'closing_credit', width: 140, render: amountRender },
          ]}
        />
      ),
    },
    {
      key: 'income-statement', label: '利润表',
      children: (
        <Table dataSource={Array.isArray((incomeStatement as any)?.items) ? (incomeStatement as any).items : []}
          rowKey="item" size="small" loading={loading} locale={{ emptyText: '暂无数据' }}
          columns={[
            { title: '项目', dataIndex: 'item', width: 200 },
            { title: '行次', dataIndex: 'line_no', width: 60 },
            { title: '金额', dataIndex: 'amount', width: 160, render: amountRender },
          ]}
        />
      ),
    },
    {
      key: 'balance-sheet', label: '资产负债表',
      children: (
        <Spin spinning={loading}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
            <Card title="资产" size="small">
              <Table dataSource={Array.isArray((balanceSheet as any)?.assets) ? (balanceSheet as any).assets : []}
                rowKey="item" size="small" pagination={false} locale={{ emptyText: '-' }}
                columns={[
                  { title: '项目', dataIndex: 'item' },
                  { title: '金额', dataIndex: 'amount', width: 140, render: amountRender },
                ]}
              />
            </Card>
            <Card title="负债及所有者权益" size="small">
              <Table dataSource={[
                ...(Array.isArray((balanceSheet as any)?.liabilities) ? (balanceSheet as any).liabilities : []),
                ...(Array.isArray((balanceSheet as any)?.equity) ? (balanceSheet as any).equity : []),
              ]} rowKey="item" size="small" pagination={false} locale={{ emptyText: '-' }}
                columns={[
                  { title: '项目', dataIndex: 'item' },
                  { title: '金额', dataIndex: 'amount', width: 140, render: amountRender },
                ]}
              />
            </Card>
          </div>
        </Spin>
      ),
    },
    {
      key: 'cash-flow', label: '现金流量表',
      children: (
        <Spin spinning={loading}>
          {(cashFlow as any)?.sections?.map((section: any, si: number) => (
            <Card key={si} title={section.section} size="small" style={{ marginBottom: 12 }}>
              <Table dataSource={section.items} rowKey="item" size="small" pagination={false} locale={{ emptyText: '-' }}
                columns={[
                  { title: '项目', dataIndex: 'item' },
                  { title: '金额', dataIndex: 'amount', width: 160, render: (v: any) => {
                    if (v == null) return '-'
                    const cls = (section.items.find((it: any) => it.item === (v != null ? '现金流量净额' : '')) || section.items.find((it: any) => it.item?.includes?.('净额')))
                    return <span style={{ color: Number(v) < 0 ? '#b91c1c' : Number(v) > 0 ? '#2d6a4f' : '#333', fontWeight: 700 }}>{amountRender(v)}</span>
                  }},
                ]}
              />
            </Card>
          ))}
        </Spin>
      ),
    },
    {
      key: 'general-ledger', label: '总账',
      children: (
        <Table dataSource={Array.isArray(generalLedger) ? generalLedger : []}
          rowKey={(_r: any, i?: number) => `gl-${i ?? 0}`}
          size="small" loading={loading} locale={{ emptyText: '暂无数据' }}
          columns={[
            { title: '日期', dataIndex: 'voucher_date', width: 110 },
            { title: '凭证号', dataIndex: 'voucher_no', width: 150 },
            { title: '摘要', dataIndex: 'summary', width: 200 },
            { title: '借方', dataIndex: 'debit', width: 140, render: amountRender },
            { title: '贷方', dataIndex: 'credit', width: 140, render: amountRender },
          ]}
        />
      ),
    },
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 24 }}>
        <h2>财务报表</h2>
        <Space>
          <Select value={period} onChange={setPeriod} style={{ width: 120 }} options={PERIODS.map(p => ({ label: p, value: p }))} />
          <Button icon={<DownloadOutlined />} onClick={() => handleExport('trial-balance')}>导出</Button>
        </Space>
      </div>
      <Card style={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
        <Tabs items={tabItems} />
      </Card>
    </div>
  )
}
