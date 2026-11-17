import { screen, fireEvent } from '@testing-library/vue';
import { mount } from '@vue/test-utils';
import { expect, it, vi } from 'vitest';
import EvidenceSource from './EvidenceSource.vue';
it('窄屏点击定位后打开原文抽屉，关闭恢复触发焦点', async () => {
  vi.stubGlobal('matchMedia', () => ({
    matches: true,
    addEventListener() {},
    removeEventListener() {},
  }));
  const wrapper = mount(EvidenceSource, {
    attachTo: document.body,
    props: { blocks: [{ id: 'b1', page: null, text: '经核验原文' }], pageCount: 0 },
  });
  const trigger = document.createElement('button');
  document.body.append(trigger);
  trigger.focus();
  wrapper.vm.locate(['b1']);
  expect(await screen.findByRole('dialog')).toBeInTheDocument();
  expect(screen.getByText('文本段落 · b1')).toBeInTheDocument();
  await fireEvent.click(screen.getByRole('button', { name: '关闭原文' }));
  expect(document.activeElement).toBe(trigger);
  wrapper.unmount();
  trigger.remove();
  vi.unstubAllGlobals();
});
