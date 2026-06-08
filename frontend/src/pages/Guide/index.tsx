import { useState, useEffect } from 'react'
import { Card, Typography, Spin, Anchor, Button } from 'antd'
import { DownloadOutlined, BookOutlined } from '@ant-design/icons'

const { Title } = Typography

// 简易 Markdown 渲染
function renderMarkdown(md: string): string {
  let html = md
  // 标题
  html = html.replace(/^#### (.+)$/gm, '<h4>$1</h4>')
  html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>')
  html = html.replace(/^## (.+)$/gm, '<h2 id="$1">$1</h2>')
  html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>')
  // 粗体/斜体
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>')
  // 行内代码
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>')
  // 代码块
  html = html.replace(/```[\s\S]*?```/g, (m) => {
    const code = m.replace(/```\w*\n?/g, '').replace(/```$/, '')
    return `<pre><code>${code}</code></pre>`
  })
  // 水平线
  html = html.replace(/^---$/gm, '<hr>')
  // 表格
  html = html.replace(/^\|(.+)\|$/gm, (line) => {
    const cells = line.split('|').filter(c => c.trim()).map(c => {
      if (/^[-:]+$/.test(c.trim())) return ''
      return `<td>${c.trim()}</td>`
    }).join('')
    if (cells.includes('<td>')) {
      const tag = line.includes('---') ? '' : 'tr'
      return tag ? `<${tag}>${cells}</${tag}>` : ''
    }
    return `<tr>${cells}</tr>`
  })
  // 无序列表
  html = html.replace(/^[-*] (.+)$/gm, '<li>$1</li>')
  // 有序列表
  html = html.replace(/^\d+\. (.+)$/gm, '<li>$1</li>')
  // 引用
  html = html.replace(/^> (.+)$/gm, '<blockquote>$1</blockquote>')
  // 段落
  html = html.replace(/\n\n/g, '</p><p>')
  html = '<p>' + html + '</p>'
  // 清理多余的 p 标签
  html = html.replace(/<p><h/g, '<h').replace(/<\/h(\d)><\/p>/g, '</h$1>')
  html = html.replace(/<p><li>/g, '<ul><li>').replace(/<\/li><\/p>/g, '</li></ul>')
  html = html.replace(/<p><pre>/g, '<pre>').replace(/<\/pre><\/p>/g, '</pre>')
  html = html.replace(/<p><blockquote>/g, '<blockquote>').replace(/<\/blockquote><\/p>/g, '</blockquote>')
  html = html.replace(/<p><hr><\/p>/g, '<hr>')
  html = html.replace(/<p><table>/g, '<table>').replace(/<\/table><\/p>/g, '</table>')
  html = html.replace(/<p><tr>/g, '<table><tr>').replace(/<\/tr><\/p>/g, '</tr></table>')
  html = html.replace(/<p>\s*<\/p>/g, '')
  return html
}

export default function Guide() {
  const [content, setContent] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/用户手册.md')
      .then(res => res.text())
      .then(md => setContent(renderMarkdown(md)))
      .catch(() => setContent('<p>加载手册失败，请检查文件是否存在。</p>'))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 24 }}>
        <Title level={3}><BookOutlined /> 用户操作手册</Title>
        <Button icon={<DownloadOutlined />} href="/用户手册.md" download>
          下载手册 (Markdown)
        </Button>
      </div>
      <Card>
        <Spin spinning={loading}>
          <div
            className="guide-content"
            style={{
              maxWidth: 900,
              margin: '0 auto',
              lineHeight: 1.8,
              fontSize: 15,
            }}
            dangerouslySetInnerHTML={{ __html: content }}
          />
        </Spin>
      </Card>
      <style>{`
        .guide-content h1 { font-size: 28px; margin: 32px 0 16px; border-bottom: 2px solid #1677ff; padding-bottom: 8px; }
        .guide-content h2 { font-size: 22px; margin: 28px 0 12px; color: #1677ff; }
        .guide-content h3 { font-size: 18px; margin: 20px 0 8px; }
        .guide-content p { margin: 8px 0; }
        .guide-content code { background: #f5f5f5; padding: 2px 6px; border-radius: 4px; font-size: 13px; }
        .guide-content pre { background: #1e1e1e; color: #d4d4d4; padding: 16px; border-radius: 8px; overflow-x: auto; }
        .guide-content pre code { background: none; padding: 0; color: inherit; }
        .guide-content table { border-collapse: collapse; width: 100%; margin: 12px 0; }
        .guide-content table td, .guide-content table th { border: 1px solid #e8e8e8; padding: 8px 12px; text-align: left; }
        .guide-content blockquote { border-left: 4px solid #1677ff; padding: 8px 16px; margin: 12px 0; background: #f0f5ff; }
        .guide-content ul, .guide-content ol { padding-left: 24px; }
        .guide-content li { margin: 4px 0; }
        .guide-content hr { margin: 24px 0; border: none; border-top: 1px solid #e8e8e8; }
        .guide-content strong { color: #1677ff; }
      `}</style>
    </div>
  )
}
