import { useState, useEffect } from 'react'
import { Button, DatePicker, Spin, App, Typography, Space, Tabs } from 'antd'
import { PrinterOutlined } from '@ant-design/icons'
import { voucherApi, reportApi } from '@/services/api'
import { useClient } from '@/contexts/ClientContext'
import dayjs from 'dayjs'

// 金额大写转换
const CN_UPPER_DIGITS = ['零', '壹', '贰', '叁', '肆', '伍', '陆', '柒', '捌', '玖']
const CN_UNITS = ['', '拾', '佰', '仟', '万', '拾', '佰', '仟', '亿']
const CN_DEC_UNITS = ['角', '分']

function toChineseUppercase(n: number): string {
  if (n === 0) return '零元整'
  if (n < 0) return '负' + toChineseUppercase(-n)
  const str = Math.round(n * 100).toString()
  const len = str.length
  if (len <= 2) {
    const jiao = len >= 2 ? str[len - 2] : '0'
    const fen = str[len - 1]
    return `零元${CN_UPPER_DIGITS[+jiao]}角${CN_UPPER_DIGITS[+fen]}分`
  }
  const intPart = str.slice(0, len - 2)
  const decPart = str.slice(len - 2)
  let result = ''
  const intLen = intPart.length
  for (let i = 0; i < intLen; i++) {
    const digit = +intPart[i]
    const unitIdx = intLen - 1 - i
    if (digit === 0) {
      if (i < intLen - 1 && +intPart[i + 1] !== 0) result += '零'
      if (unitIdx === 4 || unitIdx === 8) result += CN_UNITS[unitIdx]
    } else {
      result += CN_UPPER_DIGITS[digit] + CN_UNITS[unitIdx]
    }
  }
  result += '元'
  const jiao = +decPart[0]
  const fen = +decPart[1]
  if (jiao === 0 && fen === 0) {
    result += '整'
  } else {
    if (jiao > 0) result += CN_UPPER_DIGITS[jiao] + '角'
    else result += '零'
    if (fen > 0) result += CN_UPPER_DIGITS[fen] + '分'
  }
  return result
}

const { Text } = Typography

// ===== 打印专用样式注入 =====
const PRINT_STYLES = `
@media print {
  @page {
    size: A4 portrait;
    margin: 15mm 12mm 15mm 20mm;
  }
  @page voucher {
    size: 240mm 150mm landscape;
    margin: 10mm 10mm 10mm 18mm;
  }
  body * { visibility: hidden; }
  .print-area, .print-area * { visibility: visible; }
  .print-area { position: absolute; left: 0; top: 0; width: 100%; }
  .no-print { display: none !important; }
  .print-voucher { page: voucher; }
  .print-page-break { page-break-before: always; }
  .print-table { border-collapse: collapse; width: 100%; font-size: 12px; }
  .print-table th, .print-table td { border: 1px solid #333; padding: 4px 6px; text-align: left; }
  .print-table .amount { text-align: right; font-family: 'Courier New', monospace; }
  .print-title { text-align: center; font-size: 18px; font-weight: bold; margin-bottom: 12px; }
  .print-subtitle { text-align: center; font-size: 12px; margin-bottom: 8px; color: #555; }
  .print-footer { text-align: right; font-size: 11px; margin-top: 12px; }
  .print-header-row { display: flex; justify-content: space-between; font-size: 11px; margin-bottom: 4px; }
}
`;

export default function PrintCenter() {
  const [loading, setLoading] = useState(false)
  const [vouchers, setVouchers] = useState<any[]>([])
  const [trialBalance, setTrialBalance] = useState<any[]>([])
  const [incomeData, setIncomeData] = useState<any>(null)
  const [balanceData, setBalanceData] = useState<any>(null)
  const [generalLedger, setGeneralLedger] = useState<any[]>([])
  const [period, setPeriod] = useState(dayjs().format('YYYY-MM'))
  const { currentClientId, clientList } = useClient()
  const { message } = App.useApp()

  const currentClient = clientList.find(c => c.id === currentClientId)

  const loadData = async () => {
    if (!currentClientId) return
    setLoading(true)
    try {
      const [vRes, tRes, iRes, bRes, glRes]: any[] = await Promise.all([
        voucherApi.list({ page: 1, page_size: 100, client_id: currentClientId, status: 'confirmed' }).catch(() => ({ items: [] })),
        reportApi.trialBalance(period).catch(() => null),
        reportApi.incomeStatement(period).catch(() => null),
        reportApi.balanceSheet(period).catch(() => null),
        reportApi.generalLedger(period).catch(() => ({ ledger: [] })),
      ])
      setVouchers(vRes?.items || [])
      if (tRes?.rows) setTrialBalance(tRes.rows)
      if (iRes) setIncomeData(iRes)
      if (bRes) setBalanceData(bRes)
      if (glRes?.ledger) setGeneralLedger(glRes.ledger)
      else if (glRes?.items) setGeneralLedger(glRes.items)
    } catch { message.error('加载数据失败') }
    setLoading(false)
  }

  useEffect(() => {
    loadData()
    const style = document.createElement('style')
    style.textContent = PRINT_STYLES
    document.head.appendChild(style)
    return () => { document.head.removeChild(style) }
  }, [currentClientId, period])

  // ===== 记账凭证打印（国标格式） =====
  const renderVoucherPrint = (v: any) => {
    const entries = v.entries || []
    const totalDebit = v.total_debit || 0
    const totalCredit = v.total_credit || 0
    const voucherWord = v.voucher_no?.replace(/\d/g, '') || '记'
    const voucherNum = v.voucher_no?.replace(/\D/g, '') || ''
    return (
      <div key={v.id} className="print-voucher">
        <div className="print-title">记 账 凭 证</div>
        <div className="print-header-row">
          <span>{voucherWord}字第 {voucherNum} 号</span>
          <span>日期：{v.voucher_date}</span>
          <span>附单据 ______ 张</span>
        </div>
        <table className="print-table">
          <thead>
            <tr>
              <th style={{ width: '32%' }}>摘要</th>
              <th style={{ width: '14%' }}>总账科目</th>
              <th style={{ width: '16%' }}>明细科目</th>
              <th style={{ width: '14%' }} className="amount">借方金额</th>
              <th style={{ width: '14%' }} className="amount">贷方金额</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((e: any, i: number) => (
              <tr key={i}>
                <td>{e.summary || v.summary}</td>
                <td>{e.account_name || e.account_code}</td>
                <td>{e.account_code}</td>
                <td className="amount">{e.debit ? `¥${e.debit.toLocaleString()}` : ''}</td>
                <td className="amount">{e.credit ? `¥${e.credit.toLocaleString()}` : ''}</td>
              </tr>
            ))}
            <tr style={{ fontWeight: 'bold', borderTop: '2px solid #333' }}>
              <td colSpan={3}>
                合　计　<strong style={{ marginLeft: 8 }}>{toChineseUppercase(totalDebit)}</strong>
              </td>
              <td className="amount">¥{totalDebit.toLocaleString()}</td>
              <td className="amount">¥{totalCredit.toLocaleString()}</td>
            </tr>
          </tbody>
        </table>
        <div className="print-footer" style={{ display: 'flex', justifyContent: 'space-between', marginTop: 24, fontSize: 11 }}>
          <span>会计主管：__________</span>
          <span>记　账：__________</span>
          <span>出　纳：__________</span>
          <span>审　核：{v.reviewer || '__________'}</span>
          <span>制　单：{v.created_by || '__________'}</span>
        </div>
        <div className="print-page-break" />
      </div>
    )
  }

  // ===== 总账打印 =====
  const renderGeneralLedgerPrint = () => {
    const groups: Record<string, any[]> = {}
    for (const item of generalLedger) {
      const code = item.account_code || item.code || ''
      if (!groups[code]) groups[code] = []
      groups[code].push(item)
    }
    return Object.entries(groups).map(([code, items]) => (
      <div key={code} className="print-page-break">
        <div className="print-title">总 账</div>
        <div className="print-subtitle">科目：{items[0]?.account_name || items[0]?.name || code}（{code}）&nbsp;&nbsp; 期间：{period}</div>
        <table className="print-table">
          <thead>
            <tr>
              <th style={{ width: '12%' }}>日期</th>
              <th style={{ width: '15%' }}>凭证号</th>
              <th style={{ width: '28%' }}>摘要</th>
              <th style={{ width: '15%' }} className="amount">借方</th>
              <th style={{ width: '15%' }} className="amount">贷方</th>
              <th style={{ width: '15%' }} className="amount">余额</th>
            </tr>
          </thead>
          <tbody>
            {items.map((it, i) => (
              <tr key={i}>
                <td>{it.date || it.voucher_date || ''}</td>
                <td>{it.voucher_no || ''}</td>
                <td>{it.summary || it.description || ''}</td>
                <td className="amount">{it.debit ? `¥${Number(it.debit).toLocaleString()}` : ''}</td>
                <td className="amount">{it.credit ? `¥${Number(it.credit).toLocaleString()}` : ''}</td>
                <td className="amount">{it.balance != null ? `¥${Number(it.balance).toLocaleString()}` : ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="print-footer" style={{ display: 'flex', justifyContent: 'space-between', marginTop: 20 }}>
          <span>会计：__________</span>
          <span>复核：__________</span>
          <span>第 ___ 页</span>
        </div>
      </div>
    ))
  }

  // ===== 科目余额表打印 =====
  const renderTrialBalancePrint = () => (
    <div>
      <div className="print-title">科 目 余 额 表</div>
      <div className="print-subtitle">期间：{period} &nbsp;&nbsp; 单位：{currentClient?.name || ''}</div>
      <table className="print-table">
        <thead>
          <tr>
            <th>科目编码</th><th>科目名称</th>
            <th className="amount">期初借方</th><th className="amount">期初贷方</th>
            <th className="amount">本期借方</th><th className="amount">本期贷方</th>
            <th className="amount">期末借方</th><th className="amount">期末贷方</th>
          </tr>
        </thead>
        <tbody>
          {trialBalance.map((row: any, i: number) => (
            <tr key={i}>
              <td>{row.account_code || row.code}</td>
              <td>{row.account_name || row.name}</td>
              <td className="amount">{Number(row.begin_debit || 0).toLocaleString()}</td>
              <td className="amount">{Number(row.begin_credit || 0).toLocaleString()}</td>
              <td className="amount">{Number(row.period_debit || 0).toLocaleString()}</td>
              <td className="amount">{Number(row.period_credit || 0).toLocaleString()}</td>
              <td className="amount">{Number(row.end_debit || 0).toLocaleString()}</td>
              <td className="amount">{Number(row.end_credit || 0).toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )

  // ===== 利润表打印 =====
  const renderIncomePrint = () => {
    const d = incomeData
    if (!d) return <Text type="secondary">暂无数据</Text>
    return (
      <div>
        <div className="print-title">利 润 表</div>
        <div className="print-subtitle">期间：{period} &nbsp;&nbsp; 单位：{currentClient?.name || ''} &nbsp;&nbsp; 单位：元</div>
        <table className="print-table">
          <thead>
            <tr><th style={{ width: '60%' }}>项目</th><th style={{ width: '20%' }} className="amount">本期金额</th><th style={{ width: '20%' }} className="amount">本年累计</th></tr>
          </thead>
          <tbody>
            <tr><td>一、营业收入</td><td className="amount">{Number(d.operating_revenue || d.revenue || 0).toLocaleString()}</td><td className="amount">{Number(d.cumulative_revenue || 0).toLocaleString()}</td></tr>
            <tr><td>减：营业成本</td><td className="amount">{Number(d.operating_cost || d.cost || 0).toLocaleString()}</td><td className="amount">{Number(d.cumulative_cost || 0).toLocaleString()}</td></tr>
            <tr><td>减：税金及附加</td><td className="amount">{Number(d.tax_surcharge || 0).toLocaleString()}</td><td className="amount">{Number(d.cumulative_tax_surcharge || 0).toLocaleString()}</td></tr>
            <tr><td>减：销售费用</td><td className="amount">{Number(d.selling_expense || 0).toLocaleString()}</td><td className="amount">{Number(d.cumulative_selling_expense || 0).toLocaleString()}</td></tr>
            <tr><td>减：管理费用</td><td className="amount">{Number(d.admin_expense || 0).toLocaleString()}</td><td className="amount">{Number(d.cumulative_admin_expense || 0).toLocaleString()}</td></tr>
            <tr><td>减：财务费用</td><td className="amount">{Number(d.finance_expense || 0).toLocaleString()}</td><td className="amount">{Number(d.cumulative_finance_expense || 0).toLocaleString()}</td></tr>
            <tr><td>二、营业利润</td><td className="amount">{Number(d.operating_profit || 0).toLocaleString()}</td><td className="amount">{Number(d.cumulative_operating_profit || 0).toLocaleString()}</td></tr>
            <tr><td>加：营业外收入</td><td className="amount">{Number(d.non_operating_income || 0).toLocaleString()}</td><td className="amount">{Number(d.cumulative_non_operating_income || 0).toLocaleString()}</td></tr>
            <tr><td>减：营业外支出</td><td className="amount">{Number(d.non_operating_expense || 0).toLocaleString()}</td><td className="amount">{Number(d.cumulative_non_operating_expense || 0).toLocaleString()}</td></tr>
            <tr><td>三、利润总额</td><td className="amount">{Number(d.total_profit || 0).toLocaleString()}</td><td className="amount">{Number(d.cumulative_total_profit || 0).toLocaleString()}</td></tr>
            <tr><td>减：所得税费用</td><td className="amount">{Number(d.income_tax || 0).toLocaleString()}</td><td className="amount">{Number(d.cumulative_income_tax || 0).toLocaleString()}</td></tr>
            <tr style={{ fontWeight: 'bold' }}><td>四、净利润</td><td className="amount">{Number(d.net_profit || 0).toLocaleString()}</td><td className="amount">{Number(d.cumulative_net_profit || 0).toLocaleString()}</td></tr>
          </tbody>
        </table>
      </div>
    )
  }

  // ===== 资产负债表打印 =====
  const renderBalancePrint = () => {
    const d = balanceData
    if (!d) return <Text type="secondary">暂无数据</Text>
    return (
      <div>
        <div className="print-title">资 产 负 债 表</div>
        <div className="print-subtitle">截至：{period} &nbsp;&nbsp; 单位：{currentClient?.name || ''} &nbsp;&nbsp; 单位：元</div>
        <table className="print-table">
          <thead>
            <tr><th style={{ width: '35%' }}>资产</th><th style={{ width: '15%' }} className="amount">期末余额</th><th style={{ width: '35%' }}>负债和所有者权益</th><th style={{ width: '15%' }} className="amount">期末余额</th></tr>
          </thead>
          <tbody>
            <tr><td>货币资金</td><td className="amount">{Number(d.cash || d.monetary_funds || 0).toLocaleString()}</td><td>短期借款</td><td className="amount">{Number(d.short_term_loans || 0).toLocaleString()}</td></tr>
            <tr><td>应收账款</td><td className="amount">{Number(d.receivables || d.accounts_receivable || 0).toLocaleString()}</td><td>应付账款</td><td className="amount">{Number(d.payables || d.accounts_payable || 0).toLocaleString()}</td></tr>
            <tr><td>存货</td><td className="amount">{Number(d.inventory || 0).toLocaleString()}</td><td>应付职工薪酬</td><td className="amount">{Number(d.payroll_payable || 0).toLocaleString()}</td></tr>
            <tr><td>固定资产</td><td className="amount">{Number(d.fixed_assets || 0).toLocaleString()}</td><td>应交税费</td><td className="amount">{Number(d.tax_payable || 0).toLocaleString()}</td></tr>
            <tr style={{ fontWeight: 'bold' }}><td>资产总计</td><td className="amount">{Number(d.total_assets || 0).toLocaleString()}</td><td>负债和所有者权益总计</td><td className="amount">{Number(d.total_liabilities_equity || 0).toLocaleString()}</td></tr>
          </tbody>
        </table>
      </div>
    )
  }

  // ===== 明细账打印 =====
  const renderDetailLedgerPrint = () => (
    <div>
      <div className="print-title">明 细 账</div>
      <div className="print-subtitle">期间：{period} &nbsp;&nbsp; 单位：{currentClient?.name || ''}</div>
      <table className="print-table">
        <thead>
          <tr>
            <th style={{ width: '10%' }}>日期</th><th style={{ width: '15%' }}>凭证号</th>
            <th style={{ width: '25%' }}>摘要</th><th style={{ width: '12%' }}>科目</th>
            <th style={{ width: '12%' }} className="amount">借方</th><th style={{ width: '12%' }} className="amount">贷方</th>
            <th style={{ width: '14%' }} className="amount">方向</th>
          </tr>
        </thead>
        <tbody>
          {generalLedger.map((row: any, i: number) => (
            <tr key={i}>
              <td>{row.date || row.voucher_date || ''}</td>
              <td>{row.voucher_no || ''}</td>
              <td>{row.summary || row.description || ''}</td>
              <td>{row.account_name || row.name || ''}</td>
              <td className="amount">{row.debit ? `¥${Number(row.debit).toLocaleString()}` : ''}</td>
              <td className="amount">{row.credit ? `¥${Number(row.credit).toLocaleString()}` : ''}</td>
              <td className="amount">{Number(row.debit || 0) > 0 ? '借' : '贷'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 24 }}>
        <div>
          <Typography.Title level={4} style={{ margin: 0 }}>账簿打印中心</Typography.Title>
          <Text type="secondary" style={{ fontSize: 12 }}>
            当前客户：{currentClient?.name || '未选择'} &nbsp;|&nbsp; 标准格式 · 固定页数 · 左侧装订
          </Text>
        </div>
        <Space>
          <DatePicker picker="month" value={dayjs(period)} onChange={v => v && setPeriod(v.format('YYYY-MM'))} />
          <Button type="primary" icon={<PrinterOutlined />} onClick={() => window.print()}>打印全部</Button>
        </Space>
      </div>

      <Spin spinning={loading}>
        <Tabs
          defaultActiveKey="vouchers"
          items={[
            {
              key: 'vouchers',
              label: `记账凭证 (${vouchers.length})`,
              children: (
                <div className="print-area">
                  {vouchers.length === 0 ? <Text type="secondary" style={{ display: 'block', textAlign: 'center', padding: 40 }}>暂无已确认凭证</Text>
                    : vouchers.map(v => renderVoucherPrint(v))}
                </div>
              ),
            },
            {
              key: 'general-ledger',
              label: '总账',
              children: (
                <div className="print-area">
                  {generalLedger.length === 0 ? <Text type="secondary" style={{ display: 'block', textAlign: 'center', padding: 40 }}>暂无数据</Text>
                    : renderGeneralLedgerPrint()}
                </div>
              ),
            },
            {
              key: 'detail-ledger',
              label: '明细账',
              children: (
                <div className="print-area">
                  {generalLedger.length === 0 ? <Text type="secondary" style={{ display: 'block', textAlign: 'center', padding: 40 }}>暂无数据</Text>
                    : renderDetailLedgerPrint()}
                </div>
              ),
            },
            {
              key: 'trial-balance',
              label: '科目余额表',
              children: (
                <div className="print-area">
                  {trialBalance.length === 0 ? <Text type="secondary" style={{ display: 'block', textAlign: 'center', padding: 40 }}>暂无数据</Text>
                    : renderTrialBalancePrint()}
                </div>
              ),
            },
            {
              key: 'income-statement',
              label: '利润表',
              children: <div className="print-area">{renderIncomePrint()}</div>,
            },
            {
              key: 'balance-sheet',
              label: '资产负债表',
              children: <div className="print-area">{renderBalancePrint()}</div>,
            },
          ]}
        />
      </Spin>
    </div>
  )
}
