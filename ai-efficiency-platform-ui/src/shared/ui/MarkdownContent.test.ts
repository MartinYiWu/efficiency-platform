import { render, screen } from '@testing-library/vue';
import { describe, expect, it } from 'vitest';
import MarkdownContent from './MarkdownContent.vue';

describe('安全 Markdown 展示', () => {
  it('展示标题、表格与代码，阻断原始 HTML 和危险链接', () => {
    const { container } = render(MarkdownContent, {
      props: {
        content:
          '# 结果\n\n| 项目 | 状态 |\n| --- | --- |\n| 上传 | 完成 |\n\n```js\nconst n = 1;\n```\n\n<script>alert(1)</script>\n\n[危险](javascript:alert(1))\n\n[来源](https://example.com)',
      },
    });
    expect(screen.getByRole('heading', { name: '结果' })).toBeInTheDocument();
    expect(screen.getByRole('table')).toBeInTheDocument();
    expect(container.querySelector('pre code')).toHaveTextContent('const n = 1;');
    expect(container.querySelector('script')).toBeNull();
    expect(container.querySelector('a[href^="javascript:"]')).toBeNull();
    expect(screen.getByRole('link', { name: '来源' })).toHaveAttribute(
      'rel',
      'noopener noreferrer',
    );
  });
  it('不加载回答中的远程图片，也不允许带凭据或非 HTTPS 的外链', () => {
    const { container } = render(MarkdownContent, {
      props: {
        content:
          '![外部图片](https://example.com/a.png)\n\n[来源](http://example.com) [来源2](https://a:b@example.com)',
      },
    });
    expect(container.querySelector('img')).toBeNull();
    expect(container.querySelector('a')).toBeNull();
  });
});
