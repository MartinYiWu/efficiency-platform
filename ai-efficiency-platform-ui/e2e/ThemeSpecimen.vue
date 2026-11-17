<script setup lang="ts">
import { ref } from 'vue';
const open = ref(false);
const checked = ref(true);
const columns = [
  { title: '名称', dataIndex: 'name' },
  { title: '状态', dataIndex: 'status' },
];
</script>
<template>
  <section id="theme-specimen">
    <header class="v1-page-shell-header">
      <div>
        <h2>页面标题</h2>
        <p>页面说明</p>
      </div>
    </header>
    <a-space wrap class="specimen-row">
      <a-button id="primary-control" type="primary">主要操作</a-button>
      <a-button id="default-control">普通操作</a-button>
      <a-button id="dashed-control" type="dashed">添加技能</a-button>
      <a-button id="text-control" type="text">文字操作</a-button>
      <a-button id="disabled-control" type="primary" disabled>禁用操作</a-button>
      <a-button id="danger-control" danger>删除操作</a-button>
      <a-button id="small-control" size="small">小型操作</a-button>
    </a-space>
    <div class="specimen-field">
      <a-input id="input-control" aria-label="输入框对照" placeholder="请输入名称" />
    </div>
    <div id="select-control" class="specimen-field">
      <a-select
        aria-label="选择框对照"
        placeholder="请选择类型"
        :options="[{ value: 'a', label: '默认类型' }]"
      />
    </div>
    <div id="number-control" class="specimen-field"><a-input-number :value="10" /></div>
    <a-space
      ><span id="checkbox-control"><a-checkbox v-model:checked="checked">默认选项</a-checkbox></span
      ><a-switch id="switch-control" :checked="checked" /><span id="radio-control"
        ><a-radio checked>选择类型</a-radio></span
      ></a-space
    >
    <a-space
      ><a-tag id="tag-control">默认标签</a-tag
      ><a-tag id="tag-blue-control" color="blue">运行中</a-tag
      ><a-tag id="tag-success-control" color="success">已完成</a-tag></a-space
    >
    <a-card id="card-control" title="卡片标题"
      ><p>卡片内容</p>
      <a-button @click="open = true">打开弹窗</a-button></a-card
    >
    <div id="section-control" class="v1-section">
      <h3>业务区块</h3>
      <p>业务内容</p>
    </div>
    <div id="metric-control" class="v1-metric-card is-purple">
      <span class="v1-metric-icon">AI</span>
      <div class="v1-metric-content">
        <span class="v1-metric-title">处理数量</span><strong>128</strong
        ><em class="flat">本周统计</em>
      </div>
    </div>
    <div id="table-control">
      <a-table
        :columns="columns"
        :data-source="[{ key: 'one', name: '示例任务', status: '已完成' }]"
        :pagination="false"
      />
    </div>
    <div id="tabs-control">
      <a-tabs active-key="one"
        ><a-tab-pane key="one" tab="基础信息">基础信息内容</a-tab-pane
        ><a-tab-pane key="two" tab="版本记录">版本记录内容</a-tab-pane></a-tabs
      >
    </div>
    <a-modal v-model:open="open" title="弹窗标题" ok-text="确定" cancel-text="取消"
      ><a-input placeholder="弹窗输入框"
    /></a-modal>
  </section>
</template>
<style scoped>
#theme-specimen {
  display: flex;
  flex-direction: column;
  gap: 24px;
  padding: 24px;
  width: min(100%, 960px);
}
.specimen-field {
  width: 260px;
}
.specimen-field :deep(.ant-select) {
  width: 100%;
}
#card-control,
#section-control,
#metric-control {
  width: 360px;
}
</style>
