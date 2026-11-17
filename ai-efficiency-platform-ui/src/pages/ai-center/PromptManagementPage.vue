<script setup lang="ts">
import { ref, onMounted, watch } from 'vue';
import { useRoute } from 'vue-router';
import { message } from 'ant-design-vue';
import type { PromptDefinition, PromptDetail } from '../../entities/ai-center/model';
import {
  listPrompts,
  createPromptVersion,
  getPromptVersion,
  replacePromptContent,
} from '../../features/ai-center/api';
import { promptScopeLabel } from '../../features/ai-center/presentation';
import './ai-center.css';
const route = useRoute(),
  prompts = ref<PromptDefinition[]>([]),
  detail = ref<PromptDetail>(),
  role = ref<'SYSTEM' | 'USER' | 'ASSISTANT'>('SYSTEM'),
  content = ref(''),
  trusted = ref(false);
async function load() {
  try {
    prompts.value = await listPrompts(
      new URLSearchParams(
        route.query.agentId ? { ownerAgentId: String(route.query.agentId) } : {},
      ).toString(),
    );
  } catch (error) {
    message.error((error as Error).message);
  }
}
function showRole(nextRole: 'SYSTEM' | 'USER' | 'ASSISTANT') {
  role.value = nextRole;
  const item = detail.value?.messages.find((item) => item.role === nextRole);
  content.value = item?.contentTemplate ?? '';
  trusted.value = item?.trustedInstruction ?? false;
}
async function select(prompt: PromptDefinition) {
  try {
    const version = await createPromptVersion(prompt.id, {
      semanticVersion: `draft-${crypto.randomUUID()}`,
      changeSummary: '后台编辑草稿',
    });
    detail.value = await getPromptVersion(version.id);
    showRole('SYSTEM');
  } catch (error) {
    message.error((error as Error).message);
  }
}
async function save() {
  const currentDetail = detail.value;
  if (!currentDetail || currentDetail.version.status !== 'DRAFT') return;
  const roleMessage = currentDetail.messages.find((item) => item.role === role.value);
  const other = currentDetail.messages
    .filter((item) => item.role !== role.value)
    .map(({ ordinal, role, messageKey, contentTemplate, trustedInstruction }) => ({
      ordinal,
      role,
      messageKey,
      contentTemplate,
      trustedInstruction,
    }));
  try {
    await replacePromptContent(currentDetail.version.id, {
      messages: [
        ...other,
        {
          ordinal: roleMessage?.ordinal ?? currentDetail.messages.length + 1,
          role: role.value,
          messageKey: roleMessage?.messageKey ?? role.value.toLowerCase(),
          contentTemplate: content.value,
          trustedInstruction: trusted.value,
        },
      ].sort((a, b) => a.ordinal - b.ordinal),
      variables: currentDetail.variables.map((item) => ({
        messageKey:
          currentDetail.messages.find(
            (messageItem) => messageItem.id === item.promptMessageTemplateId,
          )?.messageKey ?? '',
        variableName: item.variableName,
        valueType: item.valueType,
        valueSource: item.valueSource,
        required: item.required,
        sensitive: item.sensitive,
        maxLength: item.maxLength,
        allowUntrustedContent: item.allowUntrustedContent,
      })),
    });
    detail.value = await getPromptVersion(currentDetail.version.id);
    message.success('Prompt 草稿已保存');
  } catch (error) {
    message.error((error as Error).message);
  }
}
onMounted(load);
watch(() => route.query.agentId, load);
</script>
<template>
  <section class="ui-page ai-page">
    <header class="ui-header">
      <div>
        <h2>Prompt 管理</h2>
        <p>共享 Prompt 与 Agent 私有 Prompt 分开归属，正文按消息角色编辑。</p>
      </div>
    </header>
    <div class="ai-columns">
      <a-card title="Prompt 资产"
        ><a-list :data-source="prompts" :locale="{ emptyText: '暂无 Prompt' }"
          ><template #renderItem="{ item }"
            ><a-list-item
              ><a-list-item-meta
                :title="item.name"
                :description="`${promptScopeLabel(item.scope)} · ${item.stageKey}`"
              /><template #actions
                ><a-button type="link" @click="select(item)">创建草稿并编辑</a-button></template
              ></a-list-item
            ></template
          ></a-list
        ></a-card
      ><a-card
        :title="
          detail ? `${detail.definition.name} · ${detail.version.semanticVersion}` : '消息编辑器'
        "
        ><a-space v-if="detail" direction="vertical" :size="16" style="width: 100%"
          ><a-select
            :value="role"
            aria-label="消息角色"
            :options="[
              { value: 'SYSTEM', label: '系统提示词（SYSTEM）' },
              { value: 'USER', label: '用户提示词（USER）' },
              { value: 'ASSISTANT', label: '助手消息（ASSISTANT）' },
            ]"
            @change="showRole"
          /><a-textarea
            v-model:value="content"
            aria-label="消息正文"
            :rows="18"
            :readonly="detail.version.status !== 'DRAFT'"
          /><a-space
            ><a-switch
              v-model:checked="trusted"
              aria-label="可信指令"
              :disabled="detail.version.status !== 'DRAFT'"
            />可信指令<a-button
              type="primary"
              :disabled="detail.version.status !== 'DRAFT'"
              @click="save"
              >保存草稿</a-button
            ></a-space
          ></a-space
        ><a-empty v-else description="选择 Prompt 后创建独立草稿版本" /></a-card
      ><a-card title="变量契约"
        ><a-form v-if="detail" layout="vertical"
          ><a-form-item
            v-for="item in detail.variables"
            :key="item.id"
            :label="item.variableName"
            :required="item.required"
            ><a-input
              :value="`${item.valueType} / ${item.valueSource}${item.sensitive ? ' / 敏感' : ''}`"
              readonly /></a-form-item></a-form
        ><a-empty v-else description="暂无变量"
      /></a-card>
    </div>
  </section>
</template>
