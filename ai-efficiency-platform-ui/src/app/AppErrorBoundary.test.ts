import { defineComponent, h } from 'vue';
import { render, screen } from '@testing-library/vue';
import { expect, it } from 'vitest';
import AppErrorBoundary from './AppErrorBoundary.vue';

it('保留子组件渲染异常的恢复提示', async () => {
  const Throwing = defineComponent({
    setup() {
      return () => {
        throw new Error('render failed');
      };
    },
  });
  render(AppErrorBoundary, { slots: { default: () => h(Throwing) } });
  expect(await screen.findByRole('alert')).toHaveTextContent('页面发生异常，请刷新后重试。');
});
