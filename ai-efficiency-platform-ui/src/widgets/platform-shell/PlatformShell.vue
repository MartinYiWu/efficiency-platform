<script setup lang="ts">
import { computed, h, onBeforeUnmount, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import {
  HomeOutlined,
  MessageOutlined,
  TeamOutlined,
  FolderOpenOutlined,
  SettingOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  UserOutlined,
} from '@ant-design/icons-vue';
import { navigation, selectedNavigation, type NavigationEntry } from './navigation';

const route = useRoute();
const router = useRouter();
const collapsed = ref(false);
const drawerOpen = ref(false);
const openGroups = ref(['assistants', 'hr', 'management']);
const shell = ref<HTMLElement>();
const chat = computed(() => route.path.endsWith('/chat'));
const selected = computed(() => selectedNavigation(route.path));
const title = computed(() => selected.value?.label ?? 'AI 效能平台');
const icons = {
  workbench: HomeOutlined,
  assistants: MessageOutlined,
  hr: TeamOutlined,
  knowledge: FolderOpenOutlined,
  management: SettingOutlined,
};
const menuItems = computed(() =>
  navigation.map((item) => ({
    key: item.key,
    label: h(
      'span',
      { 'aria-current': selected.value?.key === item.key ? 'page' : undefined },
      item.label,
    ),
    icon: () => h(icons[item.key as keyof typeof icons]),
    children: item.children?.map((child) => ({
      key: child.key,
      label: h(
        'span',
        { 'aria-current': selected.value?.key === child.key ? 'page' : undefined },
        child.label,
      ),
    })),
  })),
);
const findEntry = (key: string): NavigationEntry | undefined =>
  navigation.flatMap((item) => [item, ...(item.children ?? [])]).find((item) => item.key === key);
function navigate({ key }: { key: string | number }) {
  const entry = findEntry(String(key));
  if (entry?.path) {
    void router.push(entry.path);
    drawerOpen.value = false;
  }
}
watch(
  () => route.fullPath,
  () => {
    drawerOpen.value = false;
  },
);
const viewport = window.visualViewport;
function updateHeight() {
  if (shell.value && viewport)
    shell.value.style.setProperty('--viewport-height', `${viewport.height}px`);
}
watch([chat, shell], updateHeight, { flush: 'post' });
viewport?.addEventListener('resize', updateHeight);
onBeforeUnmount(() => viewport?.removeEventListener('resize', updateHeight));
</script>

<template>
  <div
    ref="shell"
    class="platform"
    :class="{ 'is-collapsed': collapsed, 'is-chat': chat }"
    :data-collapsed="collapsed"
  >
    <aside class="sidebar" aria-label="平台侧栏">
      <button
        class="brand"
        type="button"
        aria-label="AI效能平台，返回工作台"
        @click="router.push('/ai-assistants/hr/workbench')"
      >
        <span class="brand-mark">KM</span><span v-if="!collapsed">AI 效能平台</span>
      </button>
      <nav aria-label="平台主导航">
        <a-menu
          :items="menuItems"
          mode="inline"
          :inline-collapsed="collapsed"
          :selected-keys="selected ? [selected.key] : []"
          :open-keys="collapsed ? [] : openGroups"
          @open-change="(keys: string[]) => (openGroups = keys)"
          @click="navigate"
        />
      </nav>
    </aside>
    <div class="platform-main">
      <header class="topbar">
        <a-button
          class="desktop-toggle"
          type="text"
          :aria-label="collapsed ? '展开侧栏' : '折叠侧栏'"
          @click="collapsed = !collapsed"
          ><template #icon
            ><MenuUnfoldOutlined v-if="collapsed" /><MenuFoldOutlined v-else /></template
        ></a-button>
        <a-button
          class="mobile-toggle"
          type="text"
          aria-label="打开平台导航"
          @click="drawerOpen = true"
          ><template #icon><MenuUnfoldOutlined /></template
        ></a-button>
        <div class="location">
          <strong>{{ title }}</strong>
        </div>
        <div class="current-user">
          <a-avatar :size="30"
            ><template #icon><UserOutlined /></template></a-avatar
          ><span>内部用户</span>
        </div>
      </header>
      <main class="platform-content"><slot /></main>
    </div>
    <a-drawer
      title="AI 效能平台"
      role="dialog"
      aria-label="AI 效能平台导航"
      :aria-modal="drawerOpen"
      placement="left"
      :width="280"
      :open="drawerOpen"
      @close="drawerOpen = false"
    >
      <div v-if="drawerOpen" role="dialog" aria-label="AI 效能平台导航" aria-modal="true">
        <nav aria-label="移动端平台导航">
          <a-menu
            :items="menuItems"
            mode="inline"
            :selected-keys="selected ? [selected.key] : []"
            :open-keys="openGroups"
            @open-change="(keys: string[]) => (openGroups = keys)"
            @click="navigate"
          />
        </nav>
      </div>
    </a-drawer>
  </div>
</template>

<style scoped>
.platform {
  display: grid;
  grid-template-columns: 224px minmax(0, 1fr);
  height: var(--viewport-height, 100dvh);
  overflow: hidden;
  background: var(--v1-bg-page);
}
.platform.is-collapsed {
  grid-template-columns: 72px minmax(0, 1fr);
}
.sidebar {
  display: flex;
  min-height: 0;
  flex-direction: column;
  background: #fff;
  border-right: 1px solid var(--v1-border);
}
.brand {
  display: flex;
  height: 56px;
  flex-shrink: 0;
  align-items: center;
  gap: 10px;
  padding: 0 16px;
  border: 0;
  border-bottom: 1px solid var(--v1-border-soft);
  background: #fff;
  color: var(--v1-text);
  font-size: 17px;
  font-weight: 700;
  font-family: inherit;
  line-height: 1.6;
  white-space: nowrap;
  cursor: pointer;
}
.brand-mark {
  display: grid;
  width: 32px;
  height: 32px;
  flex: none;
  place-items: center;
  color: #fff;
  background: linear-gradient(135deg, #4f8cff 0%, #8b5cf6 100%);
  border-radius: 8px;
  font-size: 15px;
  font-weight: 800;
}
.sidebar nav {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 8px;
}
.sidebar :deep(.ant-menu) {
  border-inline-end: 0;
}
.sidebar :deep(.ant-menu-item),
.sidebar :deep(.ant-menu-submenu-title) {
  height: 38px;
  line-height: 38px;
  margin: 2px 0;
  width: 100%;
  border-radius: 6px;
  color: var(--v1-text-secondary);
}
.sidebar :deep(.ant-menu-item-selected) {
  color: var(--v1-primary);
  background: #eef5ff !important;
  font-weight: 600;
}
.platform-main {
  display: flex;
  min-width: 0;
  min-height: 0;
  flex-direction: column;
}
.topbar {
  display: flex;
  height: 56px;
  flex-shrink: 0;
  align-items: center;
  gap: 10px;
  padding: 0 16px;
  border-bottom: 1px solid var(--v1-border);
  background: rgba(255, 255, 255, 0.94);
}
.desktop-toggle,
.mobile-toggle {
  width: 34px;
  height: 34px;
  border-radius: 8px;
  color: var(--v1-text-secondary);
}
.location {
  display: flex;
  min-width: 0;
  gap: 12px;
  align-items: center;
  font-size: 13px;
  color: var(--v1-text-muted);
}
.location strong {
  overflow: hidden;
  color: var(--v1-text);
  font-size: 16px;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.current-user {
  height: 36px;
  padding: 0 8px;
  border-radius: 18px;
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
  color: var(--v1-text);
  white-space: nowrap;
  font-size: 13px;
}
.platform-content {
  min-height: 0;
  min-width: 0;
  flex: 1;
  padding: 16px;
  overflow-y: auto;
  overflow-x: hidden;
}
.is-chat .platform-content {
  display: flex;
  padding: 0;
  overflow: hidden;
}
.is-chat .platform-content > :deep(*) {
  flex: 1;
  min-height: 0;
  min-width: 0;
}
.mobile-toggle {
  display: none;
}
@media (max-width: 1023px) {
  .platform,
  .platform.is-collapsed {
    grid-template-columns: minmax(0, 1fr);
  }
  .sidebar,
  .desktop-toggle {
    display: none;
  }
  .mobile-toggle {
    display: inline-flex;
  }
  .topbar {
    padding: 0 16px;
  }
  .location > span {
    display: none;
  }
  .current-user > span:last-child {
    display: none;
  }
  .platform-content {
    padding: 14px;
  }
}
@media (max-width: 767px) {
  .topbar {
    gap: 8px;
    padding: 0 10px;
  }
  .platform-content {
    padding: 12px;
  }
}
</style>
