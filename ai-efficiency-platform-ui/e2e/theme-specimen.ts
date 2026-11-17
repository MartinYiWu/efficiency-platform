import { createApp, h } from 'vue';
import { createPinia } from 'pinia';
import Antd, { ConfigProvider } from 'ant-design-vue';
import zhCN from 'ant-design-vue/es/locale/zh_CN';
import { createMemoryHistory, createRouter } from 'vue-router';
import 'ant-design-vue/dist/reset.css';
import ThemeSpecimen from './ThemeSpecimen.vue';
import App from '../src/app/App.vue';

const reference = new URLSearchParams(window.location.search).has('reference');
if (!reference) await import('../src/app/styles/index.css');
const router = createRouter({
  history: createMemoryHistory(),
  routes: [{ path: '/', component: ThemeSpecimen }],
});
await router.push('/');
await router.isReady();
const root = reference
  ? { render: () => h(ConfigProvider, { locale: zhCN }, { default: () => h(ThemeSpecimen) }) }
  : App;
createApp(root).use(createPinia()).use(router).use(Antd).mount('#app');
document.documentElement.dataset.specimenReady = 'true';
