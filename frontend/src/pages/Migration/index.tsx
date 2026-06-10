import { useState } from 'react'
import {
  Card, Steps, Button, Upload, Table, Tag, Alert, Result, Statistic, Row, Col,
  Radio, Space, Typography, App, Descriptions, Spin, Progress, Divider, Form, Input,
} from 'antd'
import {
  ExportOutlined, ImportOutlined, DownloadOutlined, UploadOutlined,
  FileExcelOutlined, CheckCircleOutlined, SwapOutlined, InboxOutlined,
  ExclamationCircleOutlined, ThunderboltOutlined, CloudDownloadOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons'
import { migrationApi } from '@/services/api'

const { Text, Title } = Typography
const { Dragger } = Upload

type Step = 'choose' | 'preview' | 'result' | 'yqy-progress'

export default function Migration() {
  const { message } = App.useApp()
  const [step, setStep] = useState<Step>('choose')
  const [direction, setDirection] = useState<'export' | 'import'>('import')
  const [format, setFormat] = useState<'excel' | 'json'>('excel')
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [conflict, setConflict] = useState('skip')
  const [report, setReport] = useState<any>(null)
  const [exportLoading, setExportLoading] = useState(false)
  const [yqyForm] = Form.useForm()
  const [yqyLoading, setYqyLoading] = useState(false)
  const [yqyProgress, setYqyProgress] = useState('')
  const [yqyResult, setYqyResult] = useState<any>(null)

  // ===== 导出 =====
  const handleExport = async (fmt: 'excel' | 'json') => {
    setExportLoading(true)
    try {
      if (fmt === 'excel') {
        const res: any = await migrationApi.exportExcel()
        const blob = new Blob([res as any], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url; a.download = 'smart_tax_export.xlsx'; a.click()
        URL.revokeObjectURL(url)
      } else {
        const res: any = await migrationApi.exportFull()
        const blob = new Blob([JSON.stringify(res, null, 2)], { type: 'application/json' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url; a.download = 'smart_tax_full_dump.json'; a.click()
        URL.revokeObjectURL(url)
      }
      message.success('数据导出成功')
    } catch { message.error('导出失败') }
    setExportLoading(false)
  }

  const handleTemplate = async () => {
    try {
      const res: any = await migrationApi.downloadTemplate()
      const blob = new Blob([res as any], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = 'smart_tax_import_template.xlsx'; a.click()
      URL.revokeObjectURL(url)
      message.success('模板下载成功')
    } catch { message.error('下载失败') }
  }

  // ===== 上传预览 =====
  const handleUpload = async () => {
    if (!file) { message.warning('请先选择文件'); return }
    setLoading(true)
    try {
      const res: any = await migrationApi.preview(file)
      setPreview(res)
      setStep('preview')
    } catch (e: any) { message.error(e?.detail || '文件解析失败') }
    setLoading(false)
  }

  // ===== 执行导入 =====
  const handleImport = async () => {
    if (!file) return
    setLoading(true)
    try {
      const res: any = await migrationApi.import(file, conflict)
      setReport(res.report || res)
      setStep('result')
      message.success('数据导入完成')
    } catch (e: any) { message.error(e?.detail || '导入失败') }
    setLoading(false)
  }

  // ===== 亿企赢自动迁移 =====
  const handleYqyAuto = async () => {
    try {
      const values = await yqyForm.validateFields()
      setYqyLoading(true)
      setStep('yqy-progress')
      setYqyProgress('正在启动 Playwright 浏览器...')
      setYqyResult(null)

      const res: any = await migrationApi.autoYqy(values.username, values.password, values.org_name, conflict)

      setYqyProgress('采集完成，正在解析导入...')
      setYqyResult(res)
      setReport(res.report)
      setStep('result')
      message.success(`迁移完成：采集 ${res.files_collected} 个文件，导入 ${res.report?.total_imported || 0} 条`)
    } catch (e: any) {
      message.error(e?.detail || '自动迁移失败')
      setStep('choose')
    }
    setYqyLoading(false)
  }

  const reset = () => {
    setStep('choose'); setFile(null); setPreview(null); setReport(null)
    setYqyResult(null); setYqyProgress('')
  }

  // ===== 选择方向 =====
  if (step === 'choose') {
    return (
      <div style={{ maxWidth: 800, margin: '0 auto', padding: 24 }}>
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <SwapOutlined style={{ fontSize: 48, color: '#2563eb' }} />
          <Title level={3} style={{ marginTop: 12 }}>换机助手</Title>
          <Text type="secondary">一键导出旧系统数据，导入本系统，快速迁移</Text>
        </div>

        <Card style={{ marginBottom: 24 }}>
          <div style={{ display: 'flex', gap: 16, justifyContent: 'center' }}>
            <Button
              size="large"
              type={direction === 'export' ? 'primary' : 'default'}
              icon={<ExportOutlined />}
              onClick={() => setDirection('export')}
              style={{ width: 160, height: 80 }}
            >
              <div>导出数据</div>
              <div style={{ fontSize: 11, color: direction === 'export' ? '#dbeafe' : '#94a3b8' }}>从本系统导出</div>
            </Button>
            <Button
              size="large"
              type={direction === 'import' ? 'primary' : 'default'}
              icon={<ImportOutlined />}
              onClick={() => setDirection('import')}
              style={{ width: 160, height: 80 }}
            >
              <div>导入数据</div>
              <div style={{ fontSize: 11, color: direction === 'import' ? '#dbeafe' : '#94a3b8' }}>迁移到本系统</div>
            </Button>
          </div>
        </Card>

        {direction === 'export' ? (
          <Card title={<Space><ExportOutlined />导出全部数据</Space>}>
            <Alert
              message="导出包含：客户信息、会计科目、记账凭证、发票、申报记录、合同、固定资产"
              type="info" showIcon style={{ marginBottom: 16 }}
            />
            <Space size={12}>
              <Button type="primary" icon={<FileExcelOutlined />} loading={exportLoading}
                onClick={() => handleExport('excel')}>
                导出 Excel
              </Button>
              <Button icon={<DownloadOutlined />} loading={exportLoading}
                onClick={() => handleExport('json')}>
                导出完整 JSON
              </Button>
            </Space>
            <div style={{ marginTop: 12 }}>
              <Text type="secondary" style={{ fontSize: 12 }}>
                Excel 适合查看/手动编辑；JSON 保留完整关联关系，适合系统间迁移
              </Text>
            </div>
          </Card>
        ) : (
          <>
            {/* 亿企赢自动迁移 — 首选 */}
            <Card
              title={<Space><ThunderboltOutlined style={{ color: '#f59e0b' }} />亿企赢·亿企代账 一键迁移</Space>}
              style={{ marginBottom: 24, border: '2px solid #f59e0b' }}
            >
              <Alert
                message="全自动：输入亿企赢账号密码 → 系统自动登录采集数据 → 导入本系统。全程无需人工操作。"
                type="success" showIcon style={{ marginBottom: 16 }}
              />
              <Form form={yqyForm} layout="inline" style={{ flexWrap: 'wrap', gap: 8 }}>
                <Form.Item name="username" label="账号" rules={[{ required: true, message: '请输入亿企赢账号' }]}>
                  <Input placeholder="手机号/账号" style={{ width: 160 }} />
                </Form.Item>
                <Form.Item name="password" label="密码" rules={[{ required: true, message: '请输入密码' }]}>
                  <Input.Password placeholder="密码" style={{ width: 160 }} />
                </Form.Item>
                <Form.Item name="org_name" label="企业名称">
                  <Input placeholder="多企业账号需指定" style={{ width: 160 }} />
                </Form.Item>
                <Form.Item>
                  <Button type="primary" icon={<CloudDownloadOutlined />}
                    onClick={handleYqyAuto} loading={yqyLoading} danger>
                    开始自动迁移
                  </Button>
                </Form.Item>
              </Form>
              <div style={{ marginTop: 12 }}>
                <Space size={4}>
                  <ClockCircleOutlined style={{ color: '#94a3b8', fontSize: 12 }} />
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    预计耗时 30-60 秒，请确保亿企赢账号可正常登录
                  </Text>
                </Space>
              </div>
            </Card>

            {/* 手动文件导入 — 备选 */}
            <Card title={<Space><UploadOutlined />从文件导入（其他软件）</Space>} style={{ marginBottom: 24 }}>
              <Alert
                message="支持从任意代账软件导出的 Excel 或本系统 JSON dump，按照模板格式填写即可"
                type="info" showIcon style={{ marginBottom: 16 }}
              />
              <div style={{ marginBottom: 16 }}>
                <Button icon={<DownloadOutlined />} onClick={handleTemplate}>下载导入模板</Button>
                <Text type="secondary" style={{ marginLeft: 12, fontSize: 12 }}>
                  模板包含示例数据，按格式填入旧系统数据即可
                </Text>
              </div>

              <Divider />

              <div style={{ marginBottom: 12 }}>
                <Text strong>选择文件格式：</Text>
                <Radio.Group value={format} onChange={e => setFormat(e.target.value)} style={{ marginLeft: 16 }}>
                  <Radio.Button value="excel">Excel (.xlsx)</Radio.Button>
                  <Radio.Button value="json">JSON (.json)</Radio.Button>
                </Radio.Group>
              </div>

              <Dragger
                accept={format === 'excel' ? '.xlsx,.xls' : '.json'}
                maxCount={1}
                beforeUpload={(f) => { setFile(f); return false }}
                onRemove={() => setFile(null)}
                fileList={file ? [{ uid: '-1', name: file.name, status: 'done' } as any] : []}
                style={{ marginBottom: 16 }}
              >
                <p className="ant-upload-drag-icon"><InboxOutlined /></p>
                <p className="ant-upload-text">点击或拖拽文件到此区域</p>
                <p className="ant-upload-hint">
                  支持 {format === 'excel' ? '.xlsx / .xls' : '.json'} 格式
                </p>
              </Dragger>

              <Button type="primary" size="large" icon={<UploadOutlined />}
                onClick={handleUpload} loading={loading} disabled={!file} block>
                预览数据
              </Button>
            </Card>

            <Card title="迁移指南" size="small">
              <Steps
                direction="vertical"
                size="small"
                current={-1}
                items={[
                  { title: '从旧系统导出数据', description: '旧代账软件通常支持导出 Excel 或备份文件' },
                  { title: '下载本系统模板并对照填列', description: '确保列名对应，必填字段完整' },
                  { title: '上传预览，确认无误后导入', description: '系统会校验数据完整性并报告冲突' },
                  { title: '导入成功后检查数据', description: '在对应功能页面抽样核对关键数据' },
                ]}
              />
            </Card>
          </>
        )}
      </div>
    )
  }

  // ===== 亿企赢自动迁移进行中 =====
  if (step === 'yqy-progress') {
    return (
      <div style={{ maxWidth: 500, margin: '120px auto', textAlign: 'center', padding: 24 }}>
        <Spin size="large" />
        <div style={{ marginTop: 24 }}>
          <CloudDownloadOutlined style={{ fontSize: 48, color: '#f59e0b' }} />
        </div>
        <Title level={4} style={{ marginTop: 16 }}>亿企赢自动迁移中</Title>
        <Text type="secondary">{yqyProgress}</Text>
        <Progress percent={99} status="active" style={{ marginTop: 16 }} showInfo={false} />
        <div style={{ marginTop: 24 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            <ClockCircleOutlined style={{ marginRight: 4 }} />
            正在登录亿企赢并采集数据，请耐心等待...
          </Text>
        </div>
      </div>
    )
  }

  // ===== 预览 =====
  if (step === 'preview' && preview) {
    const sheets = preview.format === 'json'
      ? Object.entries(preview.counts || {}).map(([k, v]) => ({ name: k, count: v as number, issues: [] }))
      : Object.entries(preview.sheets || {}).map(([name, info]: any) => ({
          name, count: info.count, issues: info.issues || [], sample: info.sample || [],
        }))

    return (
      <div style={{ maxWidth: 960, margin: '0 auto', padding: 24 }}>
        <Title level={4}>
          <FileExcelOutlined style={{ marginRight: 8 }} />
          数据预览 — {preview.filename || 'data.json'}
        </Title>
        <Text type="secondary">
          共 {preview.total_rows || Object.values(preview.counts || {}).reduce((a: number, b: any) => a + (b as number), 0)} 条记录
          {preview.format === 'json' && preview.version && ` — 来源版本: ${preview.version}`}
        </Text>

        <Row gutter={16} style={{ margin: '16px 0' }}>
          {sheets.map((s: any) => (
            <Col span={6} key={s.name}>
              <Card size="small">
                <Statistic
                  title={s.name}
                  value={s.count}
                  suffix="条"
                  valueStyle={{ color: s.issues?.length ? '#f59e0b' : '#10b981', fontSize: 20 }}
                />
                {s.issues?.length > 0 && (
                  <Tag color="orange" style={{ marginTop: 4 }}>{s.issues.length} 个问题</Tag>
                )}
              </Card>
            </Col>
          ))}
        </Row>

        {sheets.some((s: any) => s.issues?.length > 0) && (
          <Alert
            type="warning"
            showIcon
            message="数据校验发现问题"
            description={
              <ul style={{ margin: 0, paddingLeft: 16 }}>
                {sheets.filter((s: any) => s.issues?.length).map((s: any) =>
                  s.issues.map((issue: string, i: number) =>
                    <li key={`${s.name}-${i}`}>{s.name}: {issue}</li>
                  )
                )}
              </ul>
            }
            style={{ marginBottom: 16 }}
          />
        )}

        <Card title="导入选项" style={{ marginBottom: 16 }}>
          <div style={{ marginBottom: 12 }}>
            <Text strong>冲突处理策略：</Text>
            <Radio.Group value={conflict} onChange={e => setConflict(e.target.value)} style={{ marginLeft: 16 }}>
              <Radio.Button value="skip">跳过重复</Radio.Button>
              <Radio.Button value="update">更新已有</Radio.Button>
              <Radio.Button value="overwrite">清空后导入（危险）</Radio.Button>
            </Radio.Group>
          </div>
          <Text type="secondary" style={{ fontSize: 12 }}>
            「跳过重复」：相同唯一标识(税号/凭证号/科目编码)不导入 |
            「更新已有」：覆盖更新已存在的记录 |
            「清空后导入」：删除该类型全部旧数据后导入（不可逆）
          </Text>
        </Card>

        <Space>
          <Button onClick={() => setStep('choose')}>返回重选</Button>
          <Button type="primary" size="large" icon={<ImportOutlined />}
            onClick={handleImport} loading={loading}>
            确认导入
          </Button>
        </Space>
      </div>
    )
  }

  // ===== 导入结果 =====
  if (step === 'result' && report) {
    const totalImported = report.total_imported || 0
    const totalSkipped = report.total_skipped || 0
    const hasErrors = Object.values(report.errors || {}).some((e: any) => e?.length > 0)

    return (
      <div style={{ maxWidth: 800, margin: '0 auto', padding: 24 }}>
        <Result
          status={hasErrors ? 'warning' : 'success'}
          icon={hasErrors ? <ExclamationCircleOutlined /> : <CheckCircleOutlined />}
          title={yqyResult ? '亿企赢迁移完成' : '数据迁移完成'}
          subTitle={
            yqyResult
              ? `从亿企赢采集 ${yqyResult.files_collected} 个文件，导入 ${totalImported} 条，跳过 ${totalSkipped} 条，耗时 ${yqyResult.duration_seconds?.toFixed(0)} 秒`
              : `成功导入 ${totalImported} 条，跳过 ${totalSkipped} 条${hasErrors ? '（部分异常）' : ''}`
          }
        />
        {yqyResult && yqyResult.files_detail && (
          <Card title="采集明细" size="small" style={{ marginBottom: 16 }}>
            {yqyResult.files_detail.map((f: any) => (
              <Tag key={f.category} color={f.rows > 0 ? 'green' : 'default'} style={{ margin: 4 }}>
                {f.category}: {f.rows} 行 ({f.filename})
              </Tag>
            ))}
          </Card>
        )}

        <Row gutter={16} style={{ marginBottom: 24 }}>
          <Col span={8}>
            <Card><Statistic title="导入成功" value={totalImported} valueStyle={{ color: '#10b981' }} suffix="条" /></Card>
          </Col>
          <Col span={8}>
            <Card><Statistic title="跳过" value={totalSkipped} valueStyle={{ color: '#f59e0b' }} suffix="条" /></Card>
          </Col>
          <Col span={8}>
            <Card>
              <Statistic
                title="异常"
                value={Object.values(report.errors || {}).reduce((a: number, e: any) => a + (e?.length || 0), 0)}
                valueStyle={{ color: hasErrors ? '#ef4444' : '#10b981' }}
                suffix="项"
              />
            </Card>
          </Col>
        </Row>

        <Card title="明细">
          {Object.entries(report.imported || {}).map(([sheet, count]: any) => (
            <div key={sheet} style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid #f0f0f0' }}>
              <Text strong>{sheet}</Text>
              <Space>
                <Tag color="green">导入 {count}</Tag>
                {report.skipped?.[sheet] > 0 && <Tag color="orange">跳过 {report.skipped[sheet]}</Tag>}
                {report.errors?.[sheet]?.length > 0 && <Tag color="red">异常 {report.errors[sheet].length}</Tag>}
              </Space>
            </div>
          ))}
        </Card>

        {hasErrors && (
          <Card title="异常详情" style={{ marginTop: 16 }}>
            {Object.entries(report.errors || {}).filter(([, e]: any) => e?.length > 0).map(([sheet, errors]: any) => (
              <div key={sheet} style={{ marginBottom: 12 }}>
                <Text strong style={{ color: '#ef4444' }}>{sheet}</Text>
                <ul style={{ margin: '4px 0', paddingLeft: 20, fontSize: 12 }}>
                  {errors.slice(0, 10).map((e: string, i: number) => <li key={i}>{e}</li>)}
                  {errors.length > 10 && <li>...还有 {errors.length - 10} 条</li>}
                </ul>
              </div>
            ))}
          </Card>
        )}

        <div style={{ textAlign: 'center', marginTop: 24 }}>
          <Button type="primary" size="large" onClick={reset}>完成，继续迁移</Button>
        </div>
      </div>
    )
  }

  return null
}
