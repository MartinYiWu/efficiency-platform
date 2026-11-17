import { createApp, h, ref } from 'vue';
import { createPinia } from 'pinia';
import Antd from 'ant-design-vue';
import { createRouter, createWebHistory } from 'vue-router';
import 'ant-design-vue/dist/reset.css';
import '../src/app/styles/index.css';
import App from '../src/app/App.vue';
import { routes } from '../src/app/router/routes';
import MemoryCenterPage from '../src/pages/agent-memory/MemoryCenterPage.vue';
import { memoryAccessTokenKey } from '../src/entities/memory';

declare global {
  interface Window {
    __memoryAcceptanceToken?: string;
  }
}
const accessToken = ref(window.__memoryAcceptanceToken);
delete window.__memoryAcceptanceToken;
const router = createRouter({
  history: createWebHistory(),
  routes: [{ path: '/e2e/memory-api-host.html', component: MemoryCenterPage }, ...routes],
});
await router.push(window.location.pathname + window.location.search);
await router.isReady();
createApp({
  render: () =>
    h('div', [
      h(
        'div',
        { style: 'padding:6px 16px;background:#fff7ed;color:#9a3412;font-size:12px' },
        '接口联验宿主 · 非生产登录',
      ),
      h(App),
    ]),
})
  .use(createPinia())
  .use(router)
  .use(Antd)
  .provide(memoryAccessTokenKey, () => accessToken.value)
  .mount('#app');
