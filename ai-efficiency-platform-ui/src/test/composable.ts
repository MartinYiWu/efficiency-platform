import { defineComponent, h, nextTick, proxyRefs } from 'vue';
import { mount } from '@vue/test-utils';

export function mountComposable<T extends object>(factory: () => T) {
  let current!: ReturnType<typeof proxyRefs<T>>;
  const wrapper = mount(
    defineComponent({
      setup() {
        current = proxyRefs(factory());
        return () => h('div');
      },
    }),
  );
  return {
    result: {
      get current() {
        return current;
      },
    },
    unmount: () => wrapper.unmount(),
  };
}
export async function flushUpdate(action: () => unknown) {
  await action();
  await nextTick();
}
