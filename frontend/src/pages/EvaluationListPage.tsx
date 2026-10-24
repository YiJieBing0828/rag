/**
 * 评测 run 列表页：表格 + 新建 Modal + 删除 Popconfirm。
 *
 * running 状态的 run 自动 5s 轮询（在 useEvaluationRuns hook 里）。
 */

import { useEffect, useState } from 'react'
import {
  Alert,
  App,
  Button,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Table,
  Tag,
  Tooltip,
} from 'antd'
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { Link } from 'react-router-dom'
import {
  useCreateEvaluationRun,
  useDeleteEvaluationRun,
  useEvaluationDatasets,
  useEvaluationRuns,
} from '@/api/evaluation'
import type { EvaluationRunListItem } from '@/client/types.gen'

const STATUS_TAG: Record<string, { color: string; label: string }> = {
  running: { color: 'processing', label: '执行中' },
  completed: { color: 'success', label: '已完成' },
  failed: { color: 'error', label: '失败' },
}

/**
 * 空值的三种来源必须分开显示。
 *
 * 早期一律渲染成「—」，可 `null` 至少有两个来源，含义完全相反：
 * ① **算不出来**（评测中途崩了）—— 需要人去看日志；
 * ② **不适用**（该 run 全是应拒答 case，没有可评样本）—— 正常，不用管。
 * 两者都显示「—」时，故障会被当成"这项指标本来就空着"而放过（实测登记：
 * `phase10-probe-fix` 那行的 Ctx Prec. 显示「—」，实际是并发跑崩）。
 * 现在按 run 的 status 把三种情况说清楚：还在跑 / 算失败 / 无可评样本。
 */
function metricCell(v: number | null | undefined, record?: { status?: string }) {
  if (v !== null && v !== undefined) return `${(v * 100).toFixed(1)}%`
  if (record?.status === 'running') {
    return (
      <Tooltip title="还在执行，指标要等全部 case 跑完才统一计算">
        <span style={{ color: '#8c8c8c' }}>计算中</span>
      </Tooltip>
    )
  }
  if (record?.status === 'failed') {
    return (
      <Tooltip title="本次评测中途失败，指标没算出来 —— 这不是「不适用」，去后端日志搜 evaluation run failed">
        <span style={{ color: '#cf1322' }}>计算失败</span>
      </Tooltip>
    )
  }
  return (
    <Tooltip title="没有可评样本（例如该 run 全部是应拒答 case），指标本就为空">
      <span style={{ color: '#8c8c8c' }}>无可评样本</span>
    </Tooltip>
  )
}

function latencyCell(v: number | null | undefined, record?: { status?: string }) {
  if (v !== null && v !== undefined) return `${Math.round(v)} ms`
  return metricCell(null, record)
}

export function EvaluationListPage() {
  const [page, setPage] = useState(1)
  const pageSize = 20
  const { data, isLoading } = useEvaluationRuns(page, pageSize)
  const [modalOpen, setModalOpen] = useState(false)

  const columns: ColumnsType<EvaluationRunListItem> = [
    {
      title: '名称',
      dataIndex: 'name',
      render: (text, record) => <Link to={`/evaluation/runs/${record.id}`}>{text}</Link>,
    },
    {
      title: '评测集',
      dataIndex: 'dataset_name',
      width: 120,
      render: (text, r) => (
        <span>
          {text} <Tag>{r.dataset_size}</Tag>
        </span>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 120,
      render: (status: string, r) => {
        const tag = STATUS_TAG[status] ?? { color: 'default', label: status }
        if (status === 'running') {
          return (
            <Tag color={tag.color}>
              {tag.label} {r.progress_completed}/{r.progress_total}
            </Tag>
          )
        }
        return <Tag color={tag.color}>{tag.label}</Tag>
      },
    },
    { title: 'Faithfulness', dataIndex: 'faithfulness', width: 110, render: metricCell },
    { title: 'AnswerRel.', dataIndex: 'answer_relevancy', width: 110, render: metricCell },
    { title: 'Ctx Prec.', dataIndex: 'context_precision', width: 110, render: metricCell },
    { title: 'Ctx Recall', dataIndex: 'context_recall', width: 110, render: metricCell },
    { title: '引用命中', dataIndex: 'citation_hit_rate', width: 100, render: metricCell },
    { title: '拒答正确', dataIndex: 'refusal_accuracy', width: 100, render: metricCell },
    {
      title: '平均耗时',
      dataIndex: 'avg_latency_ms',
      width: 110,
      render: latencyCell,
    },
    {
      title: '首 token 延迟',
      dataIndex: 'avg_first_token_latency_ms',
      width: 110,
      render: latencyCell,
    },
    {
      title: '操作',
      width: 80,
      render: (_, record) => <DeleteRunButton runId={record.id} runName={record.name} />,
    },
  ]

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between' }}>
        <h2 style={{ margin: 0 }}>评测分析</h2>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>
          新建评测
        </Button>
      </div>
      <Table
        rowKey="id"
        loading={isLoading}
        columns={columns}
        dataSource={data?.items ?? []}
        pagination={{
          current: page,
          pageSize,
          total: data?.total ?? 0,
          onChange: (p) => setPage(p),
          showSizeChanger: false,
        }}
        // 原来硬编码 x: 1400（列宽合计恰好 1400），而容器 clientWidth 只有 1352
        // ⇒ 操作列被裁掉 48 px：「操」字截断、删除按钮只剩半个图标，且因为
        // 不触发横向滚动条，看起来像"表格少了一列"。改成 max-content：宽度由
        // 内容决定，真的放不下时才出横向滚动条。
        scroll={{ x: 'max-content' }}
      />
      <CreateRunModal open={modalOpen} onClose={() => setModalOpen(false)} />
    </div>
  )
}

function DeleteRunButton({ runId, runName }: { runId: string; runName: string }) {
  const { message } = App.useApp()
  const mutation = useDeleteEvaluationRun()
  return (
    <Popconfirm
      title={`删除评测 “${runName}”？`}
      description="该 run 及其全部 case 都会被删除"
      okType="danger"
      onConfirm={async () => {
        await mutation.mutateAsync(runId)
        message.success('已删除')
      }}
    >
      <Button type="text" danger icon={<DeleteOutlined />} />
    </Popconfirm>
  )
}

function CreateRunModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { message } = App.useApp()
  const datasets = useEvaluationDatasets()
  const mutation = useCreateEvaluationRun()
  const [form] = Form.useForm<{ name: string; dataset_name: string }>()

  const items = datasets.data?.items ?? []
  // 默认选**最小的**数据集。
  // 原来写死 dataset_name: 'seed'，而 6 个数据集里 seed 是 50 条、其余只有 3—6 条
  // ⇒ 随手填个名字点「开始评测」＝直接跑 50 次 LLM 调用。默认值就是"用户不思考时
  // 会发生的行为"，把最贵的那个设成默认，等于把成本写在按钮上。
  const smallest = items.length
    ? [...items].sort((a, b) => a.size - b.size)[0].name
    : undefined
  const selected = Form.useWatch('dataset_name', form) as string | undefined
  const selectedSize = items.find((d) => d.name === selected)?.size ?? 0

  useEffect(() => {
    if (!smallest) return
    if (!form.getFieldValue('dataset_name')) form.setFieldValue('dataset_name', smallest)
  }, [smallest, form])

  return (
    <Modal
      title="新建评测"
      open={open}
      onCancel={onClose}
      destroyOnHidden
      onOk={async () => {
        const values = await form.validateFields()
        await mutation.mutateAsync(values)
        message.success('评测已创建，后台开始执行')
        form.resetFields()
        onClose()
      }}
      confirmLoading={mutation.isPending}
      okText="开始评测"
    >
      <Form form={form} layout="vertical" initialValues={{ name: '' }}>
        <Form.Item
          name="name"
          label="评测名称"
          rules={[{ required: true, message: '请输入名称' }, { max: 256 }]}
        >
          <Input placeholder="如：接入 rerank 后" />
        </Form.Item>
        <Form.Item
          name="dataset_name"
          label="评测集"
          rules={[{ required: true, message: '请选择评测集' }]}
        >
          <Select
            loading={datasets.isLoading}
            options={items.map((d) => ({
              value: d.name,
              label: `${d.name}（${d.size} 条）`,
            }))}
            placeholder="选择评测集"
          />
        </Form.Item>
        {selectedSize > 20 && (
          <Alert
            type="warning"
            showIcon
            message={`即将执行 ${selectedSize} 条用例 ≈ ${selectedSize} 次 LLM 调用`}
            description="评测集越大越贵也越慢，调参阶段建议先用 3—6 条的小集。"
            style={{ marginBottom: 8 }}
          />
        )}
      </Form>
    </Modal>
  )
}
