<script setup lang="ts">
import { inject, onBeforeUnmount, ref, watch } from 'vue';
import {
  fieldLabels,
  MemoryApiError,
  memoryAccessTokenKey,
  memoryErrorMessage,
  type MemoryPreference,
} from '../../entities/memory';
import {
  createMemorySharingApi,
  type SharedMemoryScope,
  type SharedMemory,
  type SharingAgent,
} from '../../entities/memory/sharing';
const props = defineProps<{ items: MemoryPreference[]; authorizationVersion?: number }>();
const emit = defineEmits<{ denied: [status: number] }>();
const token = inject(memoryAccessTokenKey, () => undefined),
  api = createMemorySharingApi(token);
const open = ref(false),
  busy = ref(false),
  error = ref(''),
  success = ref('');
const scopes = ref<SharedMemoryScope[]>([]),
  shares = ref<SharedMemory[]>([]);
const active = ref<SharedMemoryScope>(),
  itemId = ref(''),
  inviteUser = ref('');
const scopeType = ref<SharedMemoryScope['scopeType']>('PROJECT'),
  departmentId = ref(''),
  approver = ref('');
const allowedAgents = ref<SharingAgent[]>(['operations']);
let generation = 0,
  controller: AbortController | undefined;
const key = () => crypto.randomUUID();
const expiry = () => new Date(Date.now() + 30 * 86400000).toISOString();
function clear() {
  generation++;
  controller?.abort();
  scopes.value = [];
  shares.value = [];
  active.value = undefined;
  itemId.value = '';
  inviteUser.value = '';
  approver.value = '';
  departmentId.value = '';
  error.value = '';
  success.value = '';
  busy.value = false;
}
function reportFailure(reason: unknown) {
  if (reason instanceof MemoryApiError && [401, 403, 404].includes(reason.status)) {
    clear();
    open.value = false;
    emit('denied', reason.status);
  }
  error.value = memoryErrorMessage(reason);
}
async function load() {
  clear();
  if (!open.value || !token()) return;
  controller = new AbortController();
  const current = generation;
  busy.value = true;
  try {
    const values = await api.scopes(controller.signal);
    if (current === generation) scopes.value = values;
  } catch (reason) {
    if (current === generation && !controller.signal.aborted) reportFailure(reason);
  } finally {
    if (current === generation) busy.value = false;
  }
}
async function select(scope: SharedMemoryScope) {
  if (busy.value) return;
  const current = generation;
  busy.value = true;
  active.value = scope;
  shares.value = [];
  error.value = '';
  try {
    const result = await api.shares(scope.id, controller?.signal);
    if (current === generation && active.value?.id === scope.id) shares.value = result;
  } catch (reason) {
    if (current === generation) reportFailure(reason);
  } finally {
    if (current === generation) busy.value = false;
  }
}
async function action(work: () => Promise<SharedMemoryScope | SharedMemory>) {
  if (busy.value) return;
  busy.value = true;
  error.value = '';
  success.value = '';
  const current = generation;
  try {
    const result = await work();
    if (current !== generation) return;
    if ('scopeType' in result) {
      scopes.value = [...scopes.value.filter((item) => item.id !== result.id), result];
      active.value = result;
      if (result.membershipStatus === 'LEFT') shares.value = [];
      success.value = '范围状态已更新，请核对审批与成员状态。';
    } else {
      shares.value = [...shares.value.filter((item) => item.id !== result.id), result];
      success.value =
        result.status === 'ACTIVE'
          ? '共享已批准，仅授权成员及指定 Agent 可用。'
          : result.status === 'REVOKED'
            ? '已撤回此共享，原私有偏好保留。'
            : '共享申请已保存，等待指定审批人批准。';
    }
  } catch (reason) {
    if (current === generation) reportFailure(reason);
  } finally {
    if (current === generation) busy.value = false;
  }
}
function create() {
  if (!approver.value.trim() || (scopeType.value === 'DEPARTMENT' && !departmentId.value.trim())) {
    error.value = '请填写审批人及必要的部门编号';
    return;
  }
  void action(() =>
    api.createScope(
      {
        scopeType: scopeType.value,
        departmentId: departmentId.value.trim() || null,
        approverUserId: approver.value.trim(),
        expiresAt: expiry(),
        idempotencyKey: key(),
      },
      controller?.signal,
    ),
  );
}
function share() {
  const item = props.items.find((record) => record.id === itemId.value);
  const scope = active.value;
  if (!item || !scope || !allowedAgents.value.length) {
    error.value = '请选择偏好与允许使用的 Agent';
    return;
  }
  const expiresAt = new Date(
    Math.min(
      new Date(scope.expiresAt).getTime(),
      item.expiresAt ? new Date(item.expiresAt).getTime() : Infinity,
    ),
  ).toISOString();
  void action(() =>
    api.share(scope, item, allowedAgents.value, expiresAt, key(), controller?.signal),
  );
}
watch(
  () => [props.authorizationVersion, token()],
  () => {
    clear();
    if (open.value) void load();
  },
  { flush: 'sync' },
);
watch(
  () => props.items.map((item) => `${item.topAgent}:${item.id}:${item.versionId}`).join('|'),
  () => {
    itemId.value = '';
  },
);
watch(open, () => {
  if (open.value) void load();
  else clear();
});
onBeforeUnmount(clear);
const scopeLabels = {
  PROJECT: '项目记忆范围',
  DEPARTMENT: '部门记忆范围',
  ORGANIZATION: '组织记忆范围',
};
</script>
<template>
  <section class="ui-card sharing-panel" aria-label="范围共享管理">
    <button type="button" :aria-expanded="open" @click="open = !open">范围共享管理</button>
    <div v-if="open">
      <p>
        共享范围只控制记忆使用，不授予项目或业务资料的访问权限。成员需本人接受邀请，共享还需审批。
      </p>
      <p v-if="error" role="alert">{{ error }}</p>
      <p v-if="success" role="status">{{ success }}</p>
      <details>
        <summary>创建记忆共享范围</summary>
        <form class="sharing-form" @submit.prevent="create">
          <label
            >范围类型<select v-model="scopeType" :disabled="busy">
              <option value="PROJECT">项目记忆范围</option>
              <option value="DEPARTMENT">部门记忆范围</option>
              <option value="ORGANIZATION">组织记忆范围</option>
            </select></label
          >
          <label
            >部门编号（部门范围必填）<input v-model="departmentId" maxlength="128" :disabled="busy"
          /></label>
          <label
            >指定审批人的用户编号<input
              v-model="approver"
              maxlength="128"
              required
              :disabled="busy"
          /></label>
          <p>有效期 30 天。审批人需具备共享审批权限，且不能由创建人自行批准。</p>
          <a-button html-type="submit" type="primary" :disabled="busy || !token()"
            >提交范围申请</a-button
          >
        </form>
      </details>
      <a-button size="small" :disabled="busy" @click="load">刷新范围</a-button>
      <p v-if="!busy && !scopes.length">暂无可管理的共享范围</p>
      <article v-for="scope in scopes" :key="scope.id" class="sharing-item">
        <strong>{{ scopeLabels[scope.scopeType] }}</strong
        ><span
          >{{ scope.status === 'ACTIVE' ? '已批准' : '待审批' }} ·
          {{
            scope.membershipStatus === 'ACTIVE'
              ? '已加入'
              : scope.membershipStatus === 'INVITED'
                ? '待接受邀请'
                : scope.membershipStatus === 'LEFT'
                  ? '已退出'
                  : '未加入'
          }}</span
        >
        <span>有效至 {{ new Date(scope.expiresAt).toLocaleString('zh-CN') }}</span>
        <a-space wrap>
          <a-button size="small" :disabled="busy" @click="select(scope)">查看共享</a-button>
          <a-button
            v-if="scope.status === 'PENDING'"
            size="small"
            :disabled="busy"
            @click="action(() => api.approveScope(scope, key(), controller?.signal))"
            >审批此范围</a-button
          >
          <a-button
            v-if="scope.membershipStatus === 'INVITED'"
            size="small"
            :disabled="busy"
            @click="action(() => api.membership(scope, 'ACCEPT', key(), controller?.signal))"
            >接受邀请</a-button
          >
          <a-popconfirm
            v-if="scope.membershipStatus === 'ACTIVE'"
            title="退出后将停用你在此范围获得的共享记忆，其他成员不受影响。"
            @confirm="action(() => api.membership(scope, 'LEAVE', key(), controller?.signal))"
            ><a-button danger size="small" :disabled="busy">退出范围</a-button></a-popconfirm
          >
        </a-space>
      </article>
      <section v-if="active" class="sharing-detail" aria-label="当前范围共享内容">
        <h4>{{ scopeLabels[active.scopeType] }} · {{ active.id }}</h4>
        <form
          class="sharing-form"
          @submit.prevent="action(() => api.invite(active!, inviteUser, key(), controller?.signal))"
        >
          <label
            >邀请用户编号<input
              v-model="inviteUser"
              maxlength="128"
              required
              :disabled="busy" /></label
          ><a-button html-type="submit" :disabled="busy || !inviteUser.trim()">邀请成员</a-button>
        </form>
        <form class="sharing-form" @submit.prevent="share">
          <label
            >申请共享已保存的偏好<select v-model="itemId" :disabled="busy">
              <option value="">请选择偏好</option>
              <option
                v-for="item in items.filter((value) => value.topAgent !== 'hr')"
                :key="item.id"
                :value="item.id"
              >
                {{ fieldLabels[item.fieldKey] }} · 版本 {{ item.revision }}
              </option>
            </select></label
          >
          <fieldset>
            <legend>允许使用的 Agent</legend>
            <label
              ><input
                v-model="allowedAgents"
                type="checkbox"
                value="operations"
                :disabled="busy"
              />内容运营助手</label
            ><label
              ><input
                v-model="allowedAgents"
                type="checkbox"
                value="customer-service"
                :disabled="busy"
              />智能客服</label
            >
          </fieldset>
          <p>仅共享所选偏好；有效期不超过来源与范围的有效期。审批前不会生效。</p>
          <a-button html-type="submit" type="primary" :disabled="busy || !itemId"
            >提交共享申请</a-button
          >
        </form>
        <article v-for="item in shares" :key="item.id" class="sharing-item">
          <strong>{{ fieldLabels[item.fieldKey] }}</strong
          ><span
            >{{
              item.status === 'ACTIVE'
                ? '已批准共享'
                : item.status === 'REVOKED'
                  ? '已撤回'
                  : '待审批'
            }}
            · {{ item.allowedAgents.join('、') }}</span
          ><span>有效至 {{ new Date(item.expiresAt).toLocaleString('zh-CN') }}</span
          ><a-button
            v-if="item.status === 'PENDING'"
            size="small"
            :disabled="busy"
            @click="action(() => api.approveShare(item, key(), controller?.signal))"
            >审批共享</a-button
          ><a-popconfirm
            v-if="item.status !== 'REVOKED'"
            title="撤回后相关成员的共享投影将停用，原私有偏好保留。"
            @confirm="action(() => api.withdrawShare(item, key(), controller?.signal))"
            ><a-button danger size="small" :disabled="busy">撤回共享</a-button></a-popconfirm
          >
        </article>
      </section>
    </div>
  </section>
</template>
<style scoped>
.sharing-panel {
  padding: 20px;
  margin-block: 16px;
}
.sharing-panel > button {
  border: 0;
  background: none;
  color: var(--ant-color-primary, #6366f1);
  cursor: pointer;
  font: inherit;
}
.sharing-form {
  display: grid;
  gap: 12px;
  margin-block: 16px;
}
label {
  display: grid;
  gap: 6px;
}
input:not([type='checkbox']),
select {
  padding: 8px;
  border: 1px solid var(--ant-color-border, #ddd);
  border-radius: 6px;
  background: var(--ant-color-bg-container, white);
  color: inherit;
}
fieldset label {
  display: inline-flex;
  margin-inline-end: 16px;
}
.sharing-item {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  padding-block: 14px;
  border-top: 1px solid var(--ant-color-border-secondary, #eee);
  overflow-wrap: anywhere;
}
.sharing-detail {
  margin-top: 20px;
  padding: 16px;
  border: 1px solid var(--ant-color-border, #ddd);
  border-radius: 8px;
  overflow-wrap: anywhere;
}
button:focus-visible {
  outline: 2px solid var(--ant-color-primary, #6366f1);
  outline-offset: 3px;
}
</style>
