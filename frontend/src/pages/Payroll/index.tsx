import { useState, useEffect } from 'react'
import { Card, Table, Button, Space, Modal, Form, Input, InputNumber, Select, App, Tabs, Tag, Badge } from 'antd'
import { PlusOutlined, CalculatorOutlined, CheckOutlined, InboxOutlined } from '@ant-design/icons'
import { payrollApi } from '@/services/api'
import { useClient } from '@/contexts/ClientContext'
import SkeletonTable from '@/components/SkeletonTable'
import EmptyState from '@/components/EmptyState'

export default function Payroll() {
  const [employees, setEmployees] = useState<any[]>([])
  const [batches, setBatches] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [empOpen, setEmpOpen] = useState(false)
  const [batchOpen, setBatchOpen] = useState(false)
  const [batchDetail, setBatchDetail] = useState<any>(null)
  const [empForm] = Form.useForm()
  const { currentClientId } = useClient()
  const { message } = App.useApp()

  const fetchData = async () => {
    if (!currentClientId) return
    setLoading(true)
    try {
      const [eRes, bRes]: any[] = await Promise.all([
        payrollApi.listEmployees({ client_id: currentClientId }),
        payrollApi.listBatches({ client_id: currentClientId }),
      ])
      setEmployees(eRes.items || [])
      setBatches(bRes.items || [])
    } catch { message.error('加载数据失败') }
    setLoading(false)
  }

  useEffect(() => { fetchData() }, [currentClientId])

  const handleAddEmployee = async () => {
    const values = await empForm.validateFields()
    await payrollApi.createEmployee({ ...values, client_id: currentClientId })
    message.success('员工添加成功')
    setEmpOpen(false); empForm.resetFields(); fetchData()
  }

  const handleGenerateBatch = async () => {
    try {
      const now = new Date()
      const period = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
      const res: any = await payrollApi.generateBatch({ client_id: currentClientId, period })
      message.success(`工资批次已生成，${res.employee_count}名员工`)
      fetchData()
    } catch (e: any) { message.error(e?.response?.data?.detail || '生成失败') }
  }

  const handleConfirmBatch = async (batchId: string) => {
    try {
      await payrollApi.confirmBatch(batchId, { confirmed_by: localStorage.getItem('user') ? JSON.parse(localStorage.getItem('user')!).display_name : '审核员' })
      message.success('工资已确认，记账凭证自动生成')
      fetchData()
    } catch { message.error('确认失败') }
  }

  const showBatchDetail = async (batchId: string) => {
    try {
      const res: any = await payrollApi.getBatch(batchId)
      setBatchDetail(res); setBatchOpen(true)
    } catch { message.error('加载失败') }
  }

  const empColumns = [
    { title: '姓名', dataIndex: 'name', width: 80 },
    { title: '职位', dataIndex: 'position', width: 100 },
    { title: '部门', dataIndex: 'department', width: 100 },
    { title: '基本工资', dataIndex: 'base_salary', width: 120, render: (v: number) => `¥${v?.toLocaleString()}` },
    { title: '社保基数', dataIndex: 'social_insurance_base', width: 120, render: (v: number) => `¥${v?.toLocaleString()}` },
    { title: '状态', dataIndex: 'status', width: 80, render: (s: string) => <Badge status={s === 'active' ? 'success' : 'default'} text={s === 'active' ? '在职' : '离职'} /> },
  ]

  const batchColumns = [
    { title: '期间', dataIndex: 'period', width: 100 },
    { title: '应发合计', dataIndex: 'total_gross', width: 130, render: (v: number) => `¥${v?.toLocaleString()}` },
    { title: '社保合计', dataIndex: 'total_social_insurance', width: 120, render: (v: number) => `¥${v?.toLocaleString()}` },
    { title: '公积金合计', dataIndex: 'total_housing_fund', width: 120, render: (v: number) => `¥${v?.toLocaleString()}` },
    { title: '个税合计', dataIndex: 'total_iit', width: 120, render: (v: number) => `¥${v?.toLocaleString()}` },
    { title: '实发合计', dataIndex: 'total_net_pay', width: 130, render: (v: number) => `¥${v?.toLocaleString()}` },
    { title: '状态', dataIndex: 'status', width: 100, render: (s: string) => <Tag color={s === 'confirmed' ? 'green' : 'default'}>{s === 'confirmed' ? '已确认' : '草稿'}</Tag> },
    { title: '操作', key: 'act', width: 160, render: (_: any, r: any) => (
        <Space>
          <Button type="link" size="small" onClick={() => showBatchDetail(r.id)}>明细</Button>
          {r.status === 'draft' && <Button type="link" size="small" icon={<CheckOutlined />} onClick={() => handleConfirmBatch(r.id)}>确认</Button>}
        </Space>
      )},
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 24 }}>
        <h2>薪酬管理</h2>
        <Space>
          <Button icon={<PlusOutlined />} onClick={() => setEmpOpen(true)}>添加员工</Button>
          <Button type="primary" icon={<CalculatorOutlined />} onClick={handleGenerateBatch}>生成工资表</Button>
        </Space>
      </div>

      <Tabs items={[
        { key: 'employees', label: '员工花名册', children:
          loading ? <SkeletonTable rows={4} columns={5} /> :
          employees.length === 0 ? <Card><EmptyState title="暂无员工" description="添加员工以计算薪酬" icon={<InboxOutlined style={{fontSize:64,color:'#d9d9d9'}} />} /></Card> :
          <Card style={{ flex: 1, overflow: 'auto', minHeight: 0 }}><Table dataSource={employees} columns={empColumns} rowKey="id" pagination={false} /></Card>
        },
        { key: 'batches', label: '工资批次', children:
          loading ? <SkeletonTable rows={4} columns={6} /> :
          batches.length === 0 ? <Card><EmptyState title="暂无工资批次" description="生成第一个工资批次" icon={<InboxOutlined style={{fontSize:64,color:'#d9d9d9'}} />} /></Card> :
          <Card style={{ flex: 1, overflow: 'auto', minHeight: 0 }}><Table dataSource={batches} columns={batchColumns} rowKey="id" pagination={false} /></Card>
        },
      ]} />

      <Modal title="添加员工" open={empOpen} onOk={handleAddEmployee} onCancel={() => setEmpOpen(false)}>
        <Form form={empForm} layout="vertical">
          <Form.Item label="姓名" name="name" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item label="职位" name="position"><Input /></Form.Item>
          <Form.Item label="部门" name="department"><Input /></Form.Item>
          <Form.Item label="基本工资" name="base_salary"><InputNumber min={0} style={{ width: '100%' }} /></Form.Item>
          <Form.Item label="社保基数" name="social_insurance_base"><InputNumber min={0} style={{ width: '100%' }} /></Form.Item>
          <Form.Item label="公积金基数" name="housing_fund_base"><InputNumber min={0} style={{ width: '100%' }} /></Form.Item>
        </Form>
      </Modal>

      <Modal title="工资明细" open={batchOpen} onCancel={() => setBatchOpen(false)} footer={null} width={800}>
        {batchDetail && (
          <Table dataSource={batchDetail.details || []} rowKey="id" size="small" pagination={false}
            summary={() => (
              <Table.Summary.Row>
                <Table.Summary.Cell index={0} colSpan={4}>合计</Table.Summary.Cell>
                <Table.Summary.Cell index={1}>¥{batchDetail.batch?.total_gross?.toLocaleString()}</Table.Summary.Cell>
                <Table.Summary.Cell index={2}>¥{batchDetail.batch?.total_iit?.toLocaleString()}</Table.Summary.Cell>
                <Table.Summary.Cell index={3}>¥{batchDetail.batch?.total_net_pay?.toLocaleString()}</Table.Summary.Cell>
              </Table.Summary.Row>
            )}
            columns={[
              { title: '姓名', dataIndex: 'employee_name', width: 80 },
              { title: '基本工资', dataIndex: 'base_salary', width: 110, render: (v: number) => `¥${v?.toLocaleString()}` },
              { title: '社保', dataIndex: 'social_insurance_personal', width: 100, render: (v: number) => `¥${v?.toLocaleString()}` },
              { title: '公积金', dataIndex: 'housing_fund_personal', width: 100, render: (v: number) => `¥${v?.toLocaleString()}` },
              { title: '应纳税所得额', dataIndex: 'taxable_income', width: 130, render: (v: number) => `¥${v?.toLocaleString()}` },
              { title: '个税', dataIndex: 'iit', width: 100, render: (v: number) => `¥${v?.toLocaleString()}` },
              { title: '实发', dataIndex: 'net_pay', width: 110, render: (v: number) => `¥${v?.toLocaleString()}` },
            ]}
          />
        )}
      </Modal>
    </div>
  )
}
