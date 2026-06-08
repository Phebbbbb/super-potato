import { Skeleton, Card, Space } from 'antd'

interface Props {
  rows?: number
  columns?: number
  showHeader?: boolean
}

export default function SkeletonTable({ rows = 5, columns = 4, showHeader = true }: Props) {
  return (
    <Card style={{ marginBottom: 24 }}>
      {showHeader && (
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 24 }}>
          <Skeleton.Input active size="small" style={{ width: 160 }} />
          <Skeleton.Button active size="small" style={{ width: 120 }} />
        </div>
      )}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {Array.from({ length: rows }).map((_, i) => (
          <Space key={i} size={24} style={{ width: '100%' }}>
            {Array.from({ length: columns }).map((_, j) => (
              <Skeleton.Input
                key={j}
                active
                size="small"
                style={{ width: j === 0 ? 180 : 100 + Math.random() * 80 }}
              />
            ))}
          </Space>
        ))}
      </div>
    </Card>
  )
}
