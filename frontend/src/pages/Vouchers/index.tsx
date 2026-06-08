import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, Table, Button, Space, Tag, Modal, Form, Input, DatePicker, Select, InputNumber, App, Descriptions, Row, Col, Typography } from 'antd'
import { PlusOutlined, RobotOutlined, CheckOutlined, EyeOutlined, QrcodeOutlined, EditOutlined, CloseOutlined, HistoryOutlined, RocketOutlined, InboxOutlined } from '@ant-design/icons'
import { voucherApi, documentApi, feedbackApi, rpaApi } from '@/services/api'
import { useClient } from '@/contexts/ClientContext'
import SkeletonTable from '@/components/SkeletonTable'
import EmptyState from '@/components/EmptyState'
import type { ColumnsType } from 'antd/es/table'

const { Text } = Typography

interface VoucherEntry {
  account_code: string
  account_name: string
  debit: number
  credit: number
  summary: string
}

export default function Vouchers() {
  const [vouchers, setVouchers] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [detailOpen, setDetailOpen] = useState(false)
  const [editOpen, setEditOpen] = useState(false)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [rejectOpen, setRejectOpen] = useState(false)
  const [rejectReason, setRejectReason] = useState('')
  const [auditOpen, setAuditOpen] = useState(false)
  const [aiModalOpen, setAiModalOpen] = useState(false)
  const [selectedVoucher, setSelectedVoucher] = useState<any>(null)
  const [auditTrail, setAuditTrail] = useState<any[]>([])
  const [documents, setDocuments] = useState<any[]>([])
  const [selectedDocs, setSelectedDocs] = useState<string[]>([])
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([])
  const [editForm] = Form.useForm()
  const [confirmForm] = Form.useForm()
  const { currentClientId } = useClient()
  const navigate = useNavigate()
  const { message } = App.useApp()

  const fetchVouchers = async () => {
    setLoading(true)
    try {
      const res: any = await voucherApi.list({ page: 1, page_size: 50, client_id: currentClientId })
      setVouchers(res.items || [])
    } catch { message.error('加载凭证列表失败') }
    setLoading(false)
  }

  useEffect(() => { fetchVouchers() }, [currentClientId])

  // === AI 生成凭证 ===
  const handleAIGenerate = async () => {
    if (selectedDocs.length === 0) {
      message.warning('请先选择原始凭证')
      return
    }
    try {
      const res: any = await voucherApi.aiGenerate(selectedDocs, currentClientId)
      message.success(`AI 凭证 ${res.voucher_no} 生成成功，请复核`)
      setAiModalOpen(false)
      fetchVouchers()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || 'AI 生成失败')
    }
  }

  // === 查看详情 ===
  const showDetail = async (record: any) => {
    setSelectedVoucher(record)
    try {
      const res: any = await voucherApi.get(record.id)
      setSelectedVoucher(res)
    } catch { /* use list data, no message needed */ }
    setDetailOpen(true)
  }

  // === 查看审计日志 ===
  const showAuditTrail = async (record: any) => {
    setSelectedVoucher(record)
    try {
      const res: any = await feedbackApi.auditTrail('voucher', record.id)
      setAuditTrail(res.trail || [])
    } catch { setAuditTrail([]) }
    setAuditOpen(true)
  }

  // === 人工修正分录 ===
  const handleEdit = (record: any) => {
    setSelectedVoucher(record)
    const entries = record.entries || []
    editForm.setFieldsValue({
      summary: record.summary,
      entries: entries.map((e: VoucherEntry, i: number) => ({
        key: i,
        account_code: e.account_code,
        account_name: e.account_name,
        debit: e.debit,
        credit: e.credit,
        summary: e.summary,
      })),
    })
    setEditOpen(true)
  }

  const handleSaveEdit = async () => {
    const values = await editForm.validateFields()
    const entries = values.entries.map((e: any) => ({
      account_code: e.account_code,
      account_name: e.account_name,
      debit: e.debit || 0,
      credit: e.credit || 0,
      summary: e.summary || '',
    }))
    try {
      if (selectedVoucher?.id) {
        await feedbackApi.correctVoucherEntries(selectedVoucher.id, {
          summary: values.summary,
          entries,
        })
        message.success('分录已修正')
      } else {
        await voucherApi.create({
          summary: values.summary,
          voucher_date: values.voucher_date,
          entries,
          client_id: currentClientId,
        })
        message.success('凭证创建成功')
      }
      setEditOpen(false)
      fetchVouchers()
    } catch (e: any) {
      const detail = e?.response?.data?.detail
      if (typeof detail === 'object') {
        message.error(`借贷不平衡: 借=${detail.total_debit}, 贷=${detail.total_credit}, 差额=${detail.diff}`)
      } else {
        message.error(detail || '保存失败')
      }
    }
  }

  // === 审核确认 ===
  const handleConfirmOpen = (record: any) => {
    setSelectedVoucher(record)
    confirmForm.resetFields()
    setConfirmOpen(true)
  }

  const handleConfirm = async () => {
    const values = await confirmForm.validateFields()
    try {
      await voucherApi.confirm(selectedVoucher.id, values)
      message.success(`凭证 ${selectedVoucher.voucher_no} 审核通过`)
      setConfirmOpen(false)
      fetchVouchers()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '确认失败')
    }
  }

  // === 批量确认 ===
  const handleBatchConfirm = () => {
    if (selectedRowKeys.length === 0) { message.warning('请先选择凭证'); return }
    Modal.confirm({
      title: '批量审核确认',
      content: `将确认 ${selectedRowKeys.length} 张凭证，确认后不可修改。`,
      onOk: async () => {
        try {
          const res: any = await voucherApi.batchConfirm(selectedRowKeys as string[], '批量审核员')
          message.success(res.message || `已确认 ${res.confirmed} 张`)
          setSelectedRowKeys([])
          fetchVouchers()
        } catch { message.error('批量确认失败') }
      },
    })
  }

  // === 全自动加工链 ===
  const [autoLoading, setAutoLoading] = useState(false)
  const handleAutoProcess = async () => {
    if (!currentClientId) { message.warning('请先选择客户'); return }
    setAutoLoading(true)
    try {
      const res: any = await rpaApi.autoProcess(currentClientId)
      Modal.info({
        title: '全自动加工完成',
        width: 600,
        content: (
          <div>
            <p style={{ fontSize: 16, fontWeight: 500, marginBottom: 12 }}>{res.summary}</p>
            {(res.details || []).map((d: string, i: number) => (
              <p key={i} style={{ margin: 4, fontFamily: 'monospace', fontSize: 13 }}>{d}</p>
            ))}
          </div>
        ),
      })
      fetchVouchers()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '自动加工失败')
    }
    setAutoLoading(false)
  }

  // === 驳回 ===
  const handleRejectOpen = (record: any) => {
    setSelectedVoucher(record)
    setRejectReason('')
    setRejectOpen(true)
  }

  const handleRejectConfirm = async () => {
    if (!rejectReason.trim()) {
      message.warning('请输入驳回原因')
      return
    }
    try {
      await feedbackApi.rejectVoucher(selectedVoucher.id, { reason: rejectReason, issues: [rejectReason] })
      message.success('凭证已驳回')
      setRejectOpen(false)
      fetchVouchers()
    } catch (e: any) { message.error(e?.response?.data?.detail || '驳回失败') }
  }

  const columns: ColumnsType<any> = [
    { title: '凭证编号', dataIndex: 'voucher_no', key: 'voucher_no', width: 140 },
    { title: '日期', dataIndex: 'voucher_date', key: 'voucher_date', width: 100 },
    { title: '摘要', dataIndex: 'summary', key: 'summary', ellipsis: true },
    {
      title: '借方合计', dataIndex: 'total_debit', key: 'total_debit', width: 120,
      render: (v: number) => v ? `¥${v.toLocaleString()}` : '-',
    },
    {
      title: '贷方合计', dataIndex: 'total_credit', key: 'total_credit', width: 120,
      render: (v: number) => v ? `¥${v.toLocaleString()}` : '-',
    },
    {
      title: '创建方式', dataIndex: 'created_by', key: 'created_by', width: 90,
      render: (by: string) => (
        <Tag icon={by === 'ai' ? <RobotOutlined /> : null} color={by === 'ai' ? 'purple' : 'default'}>
          {by === 'ai' ? 'AI' : '手工'}
        </Tag>
      ),
    },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 90,
      render: (s: string) => {
        const map: Record<string, { color: string; text: string }> = {
          draft: { color: 'blue', text: '草稿' },
          pending_review: { color: 'orange', text: '待审核' },
          confirmed: { color: 'green', text: '已确认' },
          rejected: { color: 'red', text: '已驳回' },
          cancelled: { color: 'default', text: '已作废' },
        }
        const info = map[s] || { color: 'default', text: s }
        return <Tag color={info.color}>{info.text}</Tag>
      },
    },
    {
      title: '审核人', dataIndex: 'reviewer', key: 'reviewer', width: 90,
      render: (v: string) => v || '-',
    },
    {
      title: '操作', key: 'actions', width: 260,
      render: (_: any, record: any) => (
        <Space size={0} wrap>
          <Button type="link" size="small" icon={<EyeOutlined />} onClick={() => showDetail(record)}>详情</Button>
          <Button type="link" size="small" icon={<HistoryOutlined />} onClick={() => showAuditTrail(record)}>日志</Button>
          {(record.status === 'draft' || record.status === 'pending_review') && (
            <>
              <Button type="link" size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)}>修正</Button>
              <Button type="link" size="small" icon={<CheckOutlined />} style={{ color: '#52c41a' }}
                onClick={() => handleConfirmOpen(record)}>审核</Button>
              <Button type="link" size="small" danger icon={<CloseOutlined />} onClick={() => handleRejectOpen(record)}>驳回</Button>
            </>
          )}
          <Button type="link" size="small" icon={<QrcodeOutlined />} onClick={() => navigate(`/trace?q=${record.voucher_no}`)}>QR</Button>
          {record.status !== 'confirmed' && (
            <Button type="link" size="small" danger onClick={async () => {
              try {
                await voucherApi.delete(record.id)
                message.success('凭证已删除')
                fetchVouchers()
              } catch { message.error('删除失败') }
            }}>删除</Button>
          )}
        </Space>
      ),
    },
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 24 }}>
        <h2>记账凭证</h2>
        <Space>
          <Button icon={<RocketOutlined />} loading={autoLoading} style={{ color: '#2563eb', borderColor: '#2563eb' }}
            onClick={handleAutoProcess}>
            全自动加工
          </Button>
          <Button type="primary" icon={<RobotOutlined />} onClick={() => {
            documentApi.list({ page: 1, page_size: 100, ocr_status: 'done', client_id: currentClientId }).then((res: any) => {
              setDocuments(res.items || [])
              setAiModalOpen(true)
            }).catch(() => message.error('加载原始凭证失败'))
          }}>
            AI 生成凭证
          </Button>
          <Button icon={<PlusOutlined />} onClick={() => {
            setSelectedVoucher(null)
            editForm.resetFields()
            editForm.setFieldsValue({ summary: '', entries: [{ account_code: '', account_name: '', debit: 0, credit: 0, summary: '' }] })
            setEditOpen(true)
          }}>
            手工录入
          </Button>
          {selectedRowKeys.length > 0 && (
            <Button type="primary" icon={<CheckOutlined />} style={{ background: '#52c41a' }} onClick={handleBatchConfirm}>
              批量确认 ({selectedRowKeys.length})
            </Button>
          )}
        </Space>
      </div>

      {loading ? (
        <SkeletonTable rows={6} columns={5} />
      ) : vouchers.length === 0 ? (
        <Card>
          <EmptyState
            title="暂无记账凭证"
            description="通过票据中心上传原始凭证，AI 将自动生成记账凭证"
            actionLabel="前往票据中心"
            onAction={() => navigate('/documents')}
            icon={<InboxOutlined style={{ fontSize: 64, color: '#d9d9d9' }} />}
          />
        </Card>
      ) : (
        <Card style={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
          <Table
            dataSource={vouchers}
            columns={columns}
            rowKey="id"
            rowSelection={{
              selectedRowKeys,
              onChange: setSelectedRowKeys,
              getCheckboxProps: (record: any) => ({
                disabled: record.status === 'confirmed',
              }),
            }}
            scroll={{ x: 1100 }}
          />
        </Card>
      )}

      {/* ===== AI 生成弹窗 ===== */}
      <Modal
        title="AI 智能生成记账凭证"
        open={aiModalOpen}
        onOk={handleAIGenerate}
        onCancel={() => setAiModalOpen(false)}
        width={600}
      >
        <p style={{ marginBottom: 12, color: '#666' }}>选择已 OCR 识别的原始凭证，AI 将自动生成借贷分录</p>
        <Select
          mode="multiple"
          style={{ width: '100%' }}
          placeholder="选择原始凭证"
          value={selectedDocs}
          onChange={setSelectedDocs}
          options={documents.map((d: any) => ({
            label: `${d.file_name || d.id} (${d.doc_type})`,
            value: d.id,
          }))}
        />
      </Modal>

      {/* ===== 凭证详情弹窗 ===== */}
      <Modal
        title={`凭证详情 — ${selectedVoucher?.voucher_no || ''}`}
        open={detailOpen}
        onCancel={() => setDetailOpen(false)}
        footer={null}
        width={900}
      >
        {selectedVoucher && (
          <>
            <Descriptions bordered size="small" column={3} style={{ marginBottom: 16 }}>
              <Descriptions.Item label="凭证编号">{selectedVoucher.voucher_no}</Descriptions.Item>
              <Descriptions.Item label="日期">{selectedVoucher.voucher_date}</Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag color={selectedVoucher.status === 'confirmed' ? 'green' : 'blue'}>
                  {selectedVoucher.status === 'confirmed' ? '已确认' : selectedVoucher.status}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="创建方式">{selectedVoucher.created_by}</Descriptions.Item>
              <Descriptions.Item label="审核人">{selectedVoucher.reviewer || '-'}</Descriptions.Item>
              <Descriptions.Item label="借方合计">¥{selectedVoucher.total_debit?.toLocaleString()}</Descriptions.Item>
              <Descriptions.Item label="摘要" span={2}>{selectedVoucher.summary}</Descriptions.Item>
              <Descriptions.Item label="贷方合计">¥{selectedVoucher.total_credit?.toLocaleString()}</Descriptions.Item>
            </Descriptions>
            <Table
              dataSource={(selectedVoucher.entries || []).map((e: any, i: number) => ({ ...e, key: i }))}
              columns={[
                { title: '科目编码', dataIndex: 'account_code', width: 100 },
                { title: '科目名称', dataIndex: 'account_name', width: 150 },
                { title: '摘要', dataIndex: 'summary' },
                { title: '借方金额', dataIndex: 'debit', render: (v: number) => v ? `¥${v.toLocaleString()}` : '-' },
                { title: '贷方金额', dataIndex: 'credit', render: (v: number) => v ? `¥${v.toLocaleString()}` : '-' },
              ]}
              pagination={false}
              size="small"
              summary={() => (
                <Table.Summary.Row>
                  <Table.Summary.Cell index={0} colSpan={3}>
                    <Text strong>合计</Text>
                  </Table.Summary.Cell>
                  <Table.Summary.Cell index={1}>
                    <Text strong type="danger">¥{selectedVoucher.total_debit?.toLocaleString()}</Text>
                  </Table.Summary.Cell>
                  <Table.Summary.Cell index={2}>
                    <Text strong type="success">¥{selectedVoucher.total_credit?.toLocaleString()}</Text>
                  </Table.Summary.Cell>
                </Table.Summary.Row>
              )}
            />
          </>
        )}
      </Modal>

      {/* ===== 人工修正分录弹窗 ===== */}
      <Modal
        title="人工修正记账凭证"
        open={editOpen}
        onOk={handleSaveEdit}
        onCancel={() => setEditOpen(false)}
        width={900}
        okText="保存修正"
      >
        <Form form={editForm} layout="vertical">
          <Form.Item label="凭证摘要" name="summary" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.List name="entries">
            {(fields, { add, remove }) => (
              <>
                {fields.map(({ key, name, ...rest }) => (
                  <Row key={key} gutter={8} style={{ marginBottom: 8 }} align="middle">
                    <Col span={3}>
                      <Form.Item {...rest} name={[name, 'account_code']} noStyle>
                        <Input placeholder="科目编码" />
                      </Form.Item>
                    </Col>
                    <Col span={4}>
                      <Form.Item {...rest} name={[name, 'account_name']} noStyle>
                        <Input placeholder="科目名称" />
                      </Form.Item>
                    </Col>
                    <Col span={4}>
                      <Form.Item {...rest} name={[name, 'summary']} noStyle>
                        <Input placeholder="摘要" />
                      </Form.Item>
                    </Col>
                    <Col span={4}>
                      <Form.Item {...rest} name={[name, 'debit']} noStyle>
                        <InputNumber placeholder="借方" style={{ width: '100%' }} min={0} precision={2} />
                      </Form.Item>
                    </Col>
                    <Col span={4}>
                      <Form.Item {...rest} name={[name, 'credit']} noStyle>
                        <InputNumber placeholder="贷方" style={{ width: '100%' }} min={0} precision={2} />
                      </Form.Item>
                    </Col>
                    <Col span={3}>
                      <Button danger size="small" icon={<CloseOutlined />} onClick={() => remove(name)}>删除</Button>
                    </Col>
                  </Row>
                ))}
                <Button type="dashed" onClick={() => add({ account_code: '', account_name: '', summary: '', debit: 0, credit: 0 })} block>
                  + 添加分录行
                </Button>
              </>
            )}
          </Form.List>
        </Form>
      </Modal>

      {/* ===== 审核确认弹窗 ===== */}
      <Modal
        title="审核确认记账凭证"
        open={confirmOpen}
        onOk={handleConfirm}
        onCancel={() => setConfirmOpen(false)}
        okText="审核通过"
      >
        <Form form={confirmForm} layout="vertical">
          <Form.Item label="审核人" name="reviewer" rules={[{ required: true, message: '请输入审核人姓名' }]}>
            <Input placeholder="请输入审核人姓名" />
          </Form.Item>
          <Form.Item label="审核意见" name="comment">
            <Input.TextArea rows={3} placeholder="审核意见（可选）" />
          </Form.Item>
        </Form>
        <div style={{ color: '#fa8c16', background: '#fff7e6', padding: 12, borderRadius: 8 }}>
          ⚠️ 确认后将生成 QR 追溯码并记录审计日志，不可再修改
        </div>
      </Modal>

      {/* ===== 驳回弹窗 ===== */}
      <Modal
        title="驳回凭证"
        open={rejectOpen}
        onOk={handleRejectConfirm}
        onCancel={() => setRejectOpen(false)}
        okText="确认驳回"
        okButtonProps={{ danger: true }}
      >
        <Input.TextArea
          value={rejectReason}
          onChange={e => setRejectReason(e.target.value)}
          placeholder="请输入驳回原因"
          rows={3}
        />
      </Modal>

      {/* ===== 审计日志弹窗 ===== */}
      <Modal
        title={`操作审计日志 — ${selectedVoucher?.voucher_no || ''}`}
        open={auditOpen}
        onCancel={() => setAuditOpen(false)}
        footer={null}
        width={700}
      >
        <Table
          dataSource={auditTrail}
          columns={[
            { title: '时间', dataIndex: 'created_at', key: 'created_at', width: 180 },
            { title: '操作', dataIndex: 'action', key: 'action', width: 100,
              render: (a: string) => {
                const map: Record<string, { color: string; text: string }> = {
                  created: { color: 'blue', text: '创建' },
                  corrected: { color: 'orange', text: '修正' },
                  confirmed: { color: 'green', text: '审核通过' },
                  rejected: { color: 'red', text: '驳回' },
                }
                const info = map[a] || { color: 'default', text: a }
                return <Tag color={info.color}>{info.text}</Tag>
              },
            },
            { title: '操作人', dataIndex: 'operator', key: 'operator', width: 100 },
            { title: '详情', dataIndex: 'detail', key: 'detail',
              render: (d: any) => d ? JSON.stringify(d, null, 2).substring(0, 200) : '-' },
          ]}
          rowKey="id"
          size="small"
          pagination={false}
          locale={{ emptyText: '暂无操作记录' }}
        />
      </Modal>
    </div>
  )
}
