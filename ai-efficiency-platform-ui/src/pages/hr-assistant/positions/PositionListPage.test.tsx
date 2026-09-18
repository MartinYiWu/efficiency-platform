import { render } from '@testing-library/react';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { MemoryRouter } from 'react-router';
import { describe, expect, it } from 'vitest';

import { PositionListPage } from './PositionListPage';

describe('PositionListPage', () => {
  it('uses the native table pagination with the designed total and page size', () => {
    const { container } = render(
      <ConfigProvider locale={zhCN}>
        <MemoryRouter>
          <PositionListPage />
        </MemoryRouter>
      </ConfigProvider>,
    );

    const pagination = container.querySelector('.ant-pagination');
    expect(pagination).toHaveTextContent('共 12 条');
    expect(pagination).toHaveTextContent('20 条/页');
  });
});
