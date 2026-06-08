import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { ConfigProvider, App as AntdApp } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import App from './App'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          // 主色：深蓝但不过于肃穆，带一点现代感
          colorPrimary: '#2563eb',
          colorSuccess: '#2d6a4f',
          colorWarning: '#d97706',
          colorError: '#b91c1c',
          colorInfo: '#2563eb',
          colorTextBase: '#1e293b',
          colorTextSecondary: '#64748b',
          colorBgContainer: '#ffffff',
          colorBgLayout: '#f1f5f9',
          colorBorderSecondary: '#e2e8f0',
          // 适中圆角
          borderRadius: 6,
          borderRadiusLG: 8,
          borderRadiusSM: 4,
          fontFamily: "-apple-system, BlinkMacSystemFont, 'PingFang SC', 'Microsoft YaHei', 'Helvetica Neue', sans-serif",
          fontSize: 14,
          fontSizeLG: 15,
          fontSizeSM: 13,
          lineHeight: 1.6,
          controlHeight: 36,
          controlHeightLG: 40,
          controlHeightSM: 32,
          paddingContentHorizontal: 20,
          paddingContentVertical: 16,
          boxShadow: '0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04)',
        },
        components: {
          Layout: {
            headerBg: '#1e3a5f',
            headerColor: '#ffffff',
            headerHeight: 56,
            siderBg: '#f8fafc',
          },
          Menu: {
            itemBorderRadius: 6,
            subMenuItemBorderRadius: 6,
            itemMarginInline: 8,
            itemHeight: 42,
            iconSize: 17,
            itemColor: '#475569',
            itemSelectedColor: '#2563eb',
            itemSelectedBg: '#eff6ff',
            itemHoverBg: '#f1f5f9',
            itemActiveBg: '#eff6ff',
            subMenuItemBg: 'transparent',
          },
          Card: {
            borderRadiusLG: 8,
            paddingLG: 20,
          },
          Button: {
            borderRadius: 6,
            controlHeight: 36,
            fontWeight: 400,
            primaryShadow: '0 2px 4px rgba(37,99,235,0.2)',
          },
          Table: {
            headerBg: '#f8fafc',
            headerBorderRadius: 6,
            cellPaddingBlock: 10,
            cellPaddingInline: 14,
            borderColor: '#e2e8f0',
            rowHoverBg: '#f8fafc',
          },
          Tag: {
            borderRadiusSM: 4,
          },
          Input: {
            borderRadius: 6,
            controlHeight: 36,
            paddingInline: 12,
          },
          Select: {
            borderRadius: 6,
            controlHeight: 36,
          },
          Modal: {
            borderRadiusLG: 8,
            titleFontSize: 16,
          },
          Statistic: {
            contentFontSize: 28,
            titleFontSize: 13,
          },
          Tabs: {
            cardGutter: 2,
          },
        },
      }}
    >
      <AntdApp>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </AntdApp>
    </ConfigProvider>
  </React.StrictMode>,
)
