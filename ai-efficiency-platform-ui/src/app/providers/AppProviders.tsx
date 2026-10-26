import { App as AntdApp, ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState, type ReactNode } from 'react';

interface AppProvidersProps {
  children: ReactNode;
}

export function AppProviders({ children }: AppProvidersProps): ReactNode {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            retry: 1,
            refetchOnWindowFocus: false,
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      <ConfigProvider
        locale={zhCN}
        theme={{
          token: {
            colorPrimary: '#2463eb',
            colorBgLayout: '#f5f7fb',
            colorBorder: '#e5eaf1',
            colorBorderSecondary: '#edf0f5',
            colorText: '#182230',
            colorTextSecondary: '#667085',
            borderRadius: 10,
            borderRadiusLG: 12,
            fontSize: 14,
            controlHeight: 36,
            boxShadowTertiary: '0 2px 12px rgb(16 24 40 / 4%)',
          },
          components: {
            Card: { headerFontSize: 16, bodyPadding: 20 },
            Table: { headerBg: '#f8fafc', headerColor: '#475467', cellPaddingBlock: 13 },
          },
        }}
      >
        <AntdApp>{children}</AntdApp>
      </ConfigProvider>
    </QueryClientProvider>
  );
}
