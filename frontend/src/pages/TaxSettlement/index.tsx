import { useState, useEffect } from 'react'
import { Card, Button, Space, Tag, App, Row, Col, Statistic, Typography, Table, Spin, Descriptions, Select } from 'antd'
import { CalculatorOutlined, WarningOutlined, CheckCircleOutlined, DollarOutlined, RiseOutlined, FallOutlined } from '@ant-design/icons'
import { useClient } from '@/contexts/ClientContext'
import api from '@/services/api'
import dayjs from 'dayjs'

const { Text, Title } = Typography

export default function TaxSettlement() {
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState<any>(null)
  const [selectedYear, setSelectedYear] = useState(dayjs().year() - 1)
  const { currentClientId } = useClient()
  const { message } = App.useApp()

  const fetchSettlement = async () => {
    if (!currentClientId) return
    setLoading(true)
    try {
      const res: any = await api.get('/tax/settlement-preview', { params: { client_id: currentClientId, year: selectedYear } })
      setData(res)
    } catch { message.error('加载汇算清缴数据失败') }
    setLoading(false)
  }

  useEffect(() => { fetchSettlement() }, [currentClientId, selectedYear])

  const currentYear = dayjs().year()
  const yearOptions = Array.from({ length: 5 }, (_, i) => currentYear - 1 - i)

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 24, alignItems: 'center' }}>
        <h2><CalculatorOutlined /> 汇算清缴</h2>
        <Space>
          <Select value={selectedYear} onChange={setSelectedYear} style={{ width: 120 }}
            options={yearOptions.map(y => ({ label: `${y}年度`, value: y }))} />
          <Button type="primary" icon={<CalculatorOutlined />} onClick={fetchSettlement}>
            重新计算
          </Button>
        </Space>
      </div>

      {loading ? (
        <Spin spinning><div style={{ height: 400 }} /></Spin>
      ) : data ? (
        <>
          {/* ===== 核心结算结果 ===== */}
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={8}>
              <Card size="small" style={{ background: data.balance > 0 ? '#fef2f2' : data.balance < 0 ? '#f0fdf4' : '#f8fafc' }}>
                <Statistic
                  title={<Text strong>汇算清缴结果</Text>}
                  value={data.settlement_status}
                  valueStyle={{
                    color: data.balance > 0 ? '#dc2626' : data.balance < 0 ? '#16a34a' : '#64748b',
                    fontSize: 24, fontWeight: 700,
                  }}
                  prefix={data.balance > 0 ? <RiseOutlined /> : data.balance < 0 ? <FallOutlined /> : <CheckCircleOutlined />}
                />
                <Text style={{ fontSize: 16, fontWeight: 600, color: data.balance > 0 ? '#dc2626' : data.balance < 0 ? '#16a34a' : '#64748b' }}>
                  {data.balance_label}
                </Text>
              </Card>
            </Col>
            <Col span={8}>
              <Card size="small">
                <Statistic title="全年应纳税额" value={data.annual_cit_payable} precision={0} prefix="¥" valueStyle={{ fontSize: 22, fontWeight: 700, color: '#2563eb' }} />
                <Text type="secondary" style={{ fontSize: 11 }}>{data.tax_rate_description}</Text>
              </Card>
            </Col>
            <Col span={8}>
              <Card size="small">
                <Statistic title="已预缴所得税" value={data.quarterly_prepaid_total} precision={0} prefix="¥" valueStyle={{ fontSize: 22, fontWeight: 700, color: '#16a34a' }} />
                <Text type="secondary" style={{ fontSize: 11 }}>季度预缴合计</Text>
              </Card>
            </Col>
          </Row>

          {/* ===== 经营数据 ===== */}
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={6}>
              <Card size="small"><Statistic title="年度营业收入" value={data.annual_revenue} precision={0} prefix="¥" /></Card>
            </Col>
            <Col span={6}>
              <Card size="small"><Statistic title="年度营业成本" value={data.annual_cost} precision={0} prefix="¥" /></Card>
            </Col>
            <Col span={6}>
              <Card size="small"><Statistic title="年度利润总额" value={data.annual_profit} precision={0} prefix="¥"
                valueStyle={{ color: data.annual_profit >= 0 ? '#16a34a' : '#dc2626' }} /></Card>
            </Col>
            <Col span={6}>
              <Card size="small"><Statistic title="应纳税所得额" value={data.taxable_income} precision={0} prefix="¥"
                valueStyle={{ color: '#2563eb', fontWeight: 700 }} /></Card>
            </Col>
          </Row>

          {/* ===== 纳税调整项 ===== */}
          <Card size="small" title={<Text strong style={{ fontSize: 13 }}>纳税调整项目（填报前请与会计师确认）</Text>} style={{ marginBottom: 16 }}>
            <Table
              dataSource={data.adjustments || []}
              columns={[
                { title: '调整项目', dataIndex: 'item', ellipsis: true },
                { title: '金额', dataIndex: 'amount', width: 120, align: 'right' as const, render: (v: number) => v ? `¥${v.toLocaleString()}` : '-' },
                {
                  title: '方向', dataIndex: 'direction', width: 100,
                  render: (d: string) => <Tag color={d === 'increase' ? 'orange' : 'green'}>{d === 'increase' ? '调增应纳税所得额' : '调减应纳税所得额'}</Tag>,
                },
              ]}
              rowKey="item" size="small" pagination={false}
            />
          </Card>

          {/* ===== 关键提醒 ===== */}
          <Card size="small" style={{ background: '#fefce8', borderColor: '#fde68a', marginBottom: 16 }}>
            <Space>
              <WarningOutlined style={{ color: '#d97706' }} />
              <div>
                <Text strong style={{ color: '#92400e' }}>汇算清缴提醒：</Text>
                <Text style={{ color: '#92400e' }}>
                  截止日期 {data.filing_deadline}。{data.recommendation}
                </Text>
              </div>
            </Space>
          </Card>

          {/* ===== 说明 ===== */}
          <Card size="small" title="汇算清缴说明">
            <Descriptions bordered size="small" column={2}>
              <Descriptions.Item label="适用税率">{data.tax_rate_description}</Descriptions.Item>
              <Descriptions.Item label="小微企业">{data.is_small_profit ? '是（享受优惠税率）' : '否（适用一般税率）'}</Descriptions.Item>
              <Descriptions.Item label="申报截止日">{data.filing_deadline}（次年5月31日）</Descriptions.Item>
              <Descriptions.Item label="申报方式">电子税务局在线申报或办税服务厅</Descriptions.Item>
              <Descriptions.Item label="所需资料" span={2}>
                年度财务报表、企业所得税年度纳税申报表（A类/B类）、纳税调整项目明细表
              </Descriptions.Item>
              <Descriptions.Item label="注意事项" span={2}>
                1. 汇算清缴应于年度终了之日起5个月内完成；2. 纳税调整项需依据税法规定据实填报；
                3. 资产损失税前扣除需留存备查资料；4. 享受税收优惠需留存相关证明材料
              </Descriptions.Item>
            </Descriptions>
          </Card>
        </>
      ) : (
        <Card><div style={{ textAlign: 'center', padding: 60, color: '#94a3b8' }}>
          <CalculatorOutlined style={{ fontSize: 48, marginBottom: 16 }} />
          <div>点击"重新计算"加载汇算清缴数据</div>
        </div></Card>
      )}
    </div>
  )
}
