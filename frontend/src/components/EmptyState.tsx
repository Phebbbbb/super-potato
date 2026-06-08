import { Empty, Button } from 'antd'
import { InboxOutlined } from '@ant-design/icons'

interface Props {
  title?: string
  description?: string
  actionLabel?: string
  onAction?: () => void
  icon?: React.ReactNode
}

export default function EmptyState({
  title = '暂无数据',
  description = '',
  actionLabel,
  onAction,
  icon,
}: Props) {
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      minHeight: 320,
      padding: 48,
    }}>
      <Empty
        image={icon || <InboxOutlined style={{ fontSize: 64, color: '#d9d9d9' }} />}
        description={
          <>
            <div style={{ fontSize: 16, fontWeight: 500, color: '#8c8c8c', marginBottom: 4 }}>
              {title}
            </div>
            {description && (
              <div style={{ fontSize: 13, color: '#bfbfbf' }}>{description}</div>
            )}
          </>
        }
      >
        {actionLabel && onAction && (
          <Button type="primary" onClick={onAction}>{actionLabel}</Button>
        )}
      </Empty>
    </div>
  )
}
