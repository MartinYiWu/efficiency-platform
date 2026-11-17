<script lang="ts">
import { defineComponent, ref, Fragment, type PropType, type VNodeChild } from 'vue';
import { v as hrNode } from '../hrVnodes';
import { CloseOutlined, InfoCircleFilled, LoadingOutlined } from '@ant-design/icons-vue';
import { Button, Empty, Modal, Progress, Skeleton, Typography } from 'ant-design-vue';
import styles from './HrComponentStatesPage.module.css';
const colors = [
  ['primary', '主要操作 / 紫色渐变按钮', '#9333EA → #7C3AED'],
  ['navigation', '导航 / V1 蓝色', '#2563EB'],
  ['success', '成功 / 正向', '#10B981'],
  ['warning', '警示 / 需关注', '#F59E0B'],
  ['error', '错误 / 危险', '#EF4444'],
  ['neutral', '中性 / 弱化文字', '#9CA3AF'],
  ['border', '边框 / 分割线', '#E5E7EB'],
  ['background', '背景 / V1 页面', '#F6F8FC'],
] as const;
const grades = [
  ['strong', '强烈推荐面试', '匹配度高，建议优先安排面试'],
  ['recommend', '推荐面试', '匹配度良好，建议安排面试'],
  ['review', '建议复核', '存在部分差距，建议复核后再决定'],
  ['muted', '暂不推荐', '匹配度较低，暂不建议面试'],
] as const;
const conditions = [
  ['🎓', '学历要求：本科及以上', '≥', '本科'],
  ['💼', '工作年限：3年及以上', '≥', '4.2年'],
  ['⌖', '期望城市：上海', '=', '上海'],
  ['⌘', '技能要求：Django', '包含', '是'],
  ['▣', '项目经验：电商系统开发', '包含', '是'],
  ['¥', '期望薪资：15K-25K/月', '范围', '20K'],
] as const;
const dimensions = [
  ['◉', '技能匹配', 92, 'blue'],
  ['✖', '经验匹配', 85, 'blue'],
  ['▣', '项目匹配', 90, 'blue'],
  ['🎓', '学历匹配', 80, 'blue'],
  ['♨', '加分项', 60, 'orange'],
] as const;
export const HrComponentStatesPage = defineComponent({
  name: 'HrComponentStatesPage',
  inheritAttrs: false,
  props: {},
  setup() {
    const dialog = ref<'delete' | 'release' | null>(null);
    const setDialog = (
      next: typeof dialog.value | ((current: typeof dialog.value) => typeof dialog.value),
    ) => {
      dialog.value = typeof next === 'function' ? next(dialog.value) : next;
    };
    return () => {
      return hrNode(
        'div',
        { className: [styles.page, 'ui-page'] },
        hrNode(
          'p',
          { className: styles.demoNotice, role: 'note' },
          ' 组件规范示例 · 不表示任何真实候选人结果。 ',
        ),
        hrNode(
          'div',
          { className: styles.intro },
          hrNode(Typography.Title, { level: 1 }, '页面：组件与状态规范（PAGE-00）'),
          hrNode(
            Typography.Paragraph,
            null,
            ' 本页定义 AI 人事助手在匹配结果与面试准备场景中的核心组件与状态样式，供设计与研发一致性使用。 ',
          ),
        ),
        hrNode(
          'section',
          null,
          hrNode('h2', null, '完整业务状态'),
          ...[
            'UNKNOWN · 未提及，不等于不具备',
            'NEEDS_REVIEW · 待核验，参考分不参与排名',
            'FILTERED · 被硬条件过滤，总分 —',
            'FAILED · 技术失败，不构成候选人负面结论',
            'STALE · 历史版本，刷新不自动重算',
            '面试官视图 · 仅题目、来源和提纲，不含分数评级',
          ].map((text) => hrNode('p', { key: text }, text)),
        ),
        hrNode(
          'div',
          { className: styles.twoColumn },
          hrNode(
            Panel,
            { title: '一、色彩规范' },
            hrNode(
              'div',
              { className: styles.colors },
              colors.map(([tone, label, hex]) =>
                hrNode(
                  'div',
                  { className: styles.swatch, key: label },
                  hrNode('span', { className: styles[tone] }),
                  hrNode('strong', null, label),
                  hrNode('small', null, hex),
                ),
              ),
            ),
          ),
          hrNode(
            Panel,
            { title: '二、匹配等级标签（面试建议）' },
            hrNode(
              'div',
              { className: styles.grades },
              grades.map(([tone, label, description]) =>
                hrNode(
                  'div',
                  { className: styles.gradeRow, key: label },
                  hrNode('span', { className: styles[`grade${tone}`] }, label),
                  hrNode('small', null, description),
                ),
              ),
            ),
          ),
          hrNode(
            Panel,
            { title: '三、硬性条件判断状态（示例：实际数值展示）' },
            hrNode(
              'div',
              { className: styles.conditionGrid },
              conditions.map(([icon, requirement, operator, actual]) =>
                hrNode(
                  'div',
                  { className: styles.conditionRow, key: requirement },
                  hrNode('span', null, icon),
                  hrNode('span', null, requirement),
                  hrNode('b', null, operator),
                  hrNode('span', null, actual),
                  hrNode('span', { className: styles.pass }, '满足'),
                ),
              ),
            ),
          ),
          hrNode(
            Panel,
            { title: '四、维度得分进度条（5项）' },
            hrNode(
              'div',
              { className: styles.dimensionList },
              dimensions.map(([icon, label, score, tone]) =>
                hrNode(
                  'div',
                  { className: styles.dimensionRow, key: label },
                  hrNode(
                    'span',
                    { className: tone === 'orange' ? styles.orangeIcon : styles.blueIcon },
                    icon,
                  ),
                  hrNode('span', null, label),
                  hrNode(Progress, {
                    percent: score,
                    showInfo: false,
                    strokeColor: tone === 'orange' ? '#fa8c16' : '#1677ff',
                  }),
                  hrNode('b', null, score, '/100'),
                ),
              ),
            ),
          ),
          hrNode(
            Panel,
            { title: '五、证据卡片（可点击）' },
            hrNode(
              'article',
              { className: styles.evidenceCard },
              hrNode(
                'div',
                null,
                hrNode('strong', null, '证据：具备真实的后端开发基础与系统设计实践'),
                hrNode('span', { className: styles.confident }, '强（HIGH）'),
              ),
              hrNode(
                'p',
                null,
                ' 候选人具备扎实的后端开发基础，熟悉高并发、分布式系统设计与实现。在微服务、数据库优化及缓存等方面有丰富的实践经验。 ',
              ),
              hrNode(Button, { type: 'link' }, '查看原文位置 →'),
            ),
          ),
          hrNode(
            Panel,
            { title: '六、置信度标签' },
            hrNode(
              'div',
              { className: styles.confidenceList },
              [
                ['strong', '强（HIGH）', '证据充分，结论可靠'],
                ['recommend', '中（MEDIUM）', '证据一般，结论较可靠'],
                ['muted', '弱（LOW）', '证据不足，结论需谨慎'],
              ].map(([tone, label, description]) =>
                hrNode(
                  'div',
                  { className: styles.confidenceRow, key: label },
                  hrNode('i', { className: styles[`dot${tone}`] }),
                  hrNode('span', null, label),
                  hrNode('small', null, description),
                  hrNode('span', { className: styles[`grade${tone}`] }, label),
                ),
              ),
            ),
          ),
        ),
        hrNode(
          'section',
          null,
          hrNode('h2', null, '完整业务状态'),
          ...[
            'UNKNOWN · 未提及，不等于不具备',
            'NEEDS_REVIEW · 待核验，参考分不参与排名',
            'FILTERED · 被硬条件过滤，总分 —',
            'FAILED · 技术失败，不构成候选人负面结论',
            'STALE · 历史版本，刷新不自动重算',
            '面试官视图 · 仅题目、来源和提纲，不含分数评级',
          ].map((text) => hrNode('p', { key: text }, text)),
        ),
        hrNode(
          'div',
          { className: styles.twoColumn },
          hrNode(
            Panel,
            { title: '七、按钮组件状态' },
            hrNode(
              'div',
              { className: styles.buttonMatrix },
              hrNode('span', null),
              hrNode('span', null, '主要按钮（实心）'),
              hrNode('span', null, '次要按钮（描边）'),
              hrNode('span', null, '文本按钮（链接）'),
              ['默认', '悬停', '点击', '禁用'].map((state: string, index: number) =>
                hrNode(ButtonStateRow, { key: state, state: state, disabled: index === 3 }),
              ),
            ),
            hrNode(
              'p',
              { className: styles.note },
              ' 说明：主要按钮用于核心操作；次要按钮用于辅助操作；文本按钮用于跳转或查看。 ',
            ),
          ),
          hrNode(
            Panel,
            { title: '八、表格行组件（标准行）' },
            hrNode(
              'div',
              { className: styles.tableFrame },
              hrNode(
                'table',
                { className: styles.table },
                hrNode(
                  'thead',
                  null,
                  hrNode(
                    'tr',
                    null,
                    hrNode('th', null, '候选人'),
                    hrNode('th', null, '岗位'),
                    hrNode('th', null, '匹配度'),
                    hrNode('th', null, '面试建议'),
                    hrNode('th', null, '更新时间'),
                    hrNode('th', null, '操作'),
                  ),
                ),
                hrNode(
                  'tbody',
                  null,
                  hrNode(
                    'tr',
                    null,
                    hrNode('td', null, hrNode('span', { className: styles.avatar }, '张'), '张伟 '),
                    hrNode('td', null, '后端开发工程师（P6）'),
                    hrNode('td', { className: styles.scoreNumber }, '88.5'),
                    hrNode(
                      'td',
                      null,
                      hrNode('span', { className: styles.gradeStrong }, '强烈推荐面试'),
                    ),
                    hrNode('td', null, '今天 14:35'),
                    hrNode(
                      'td',
                      null,
                      hrNode(Button, { type: 'link' }, '查看'),
                      hrNode(Button, { type: 'link' }, '删除'),
                    ),
                  ),
                ),
              ),
            ),
            hrNode(
              'p',
              { className: styles.note },
              '说明：行高 56px，分割线使用 #F0F2F5；操作链接间距 12px。',
            ),
          ),
        ),
        hrNode(
          Panel,
          { title: '九、空状态与加载状态' },
          hrNode(
            'div',
            { className: styles.stateGrid },
            hrNode(
              StateBox,
              { title: '空状态 - 无结果' },
              hrNode(Empty, { image: Empty.PRESENTED_IMAGE_SIMPLE, description: '暂无匹配结果' }),
              hrNode(Button, { type: 'link' }, '调整筛选条件，重新搜索'),
            ),
            hrNode(
              StateBox,
              { title: '空状态 - 无数据' },
              hrNode(Empty, { image: Empty.PRESENTED_IMAGE_SIMPLE, description: '暂无数据' }),
              hrNode(Button, { type: 'link' }, '去导入数据'),
            ),
            hrNode(
              StateBox,
              { title: '加载中 - 列表' },
              hrNode(LoadingOutlined, { className: styles.loadingIcon }),
              hrNode('span', null, '加载中，请稍候...'),
            ),
            hrNode(
              StateBox,
              { title: '加载中 - 区块' },
              hrNode(Skeleton, { active: true, title: { width: '55%' }, paragraph: { rows: 2 } }),
              hrNode('span', null, '加载中，请稍候...'),
            ),
            hrNode(
              StateBox,
              { title: '加载中 - 按钮' },
              hrNode(Button, { type: 'primary', loading: true }, ' 生成中... '),
            ),
          ),
        ),
        hrNode(
          'section',
          { className: styles.disclaimer },
          hrNode(InfoCircleFilled, null),
          hrNode(
            'span',
            null,
            hrNode('b', null, '十、AI 提示说明（免责声明）'),
            hrNode('br', null),
            ' AI 产出的匹配结果与建议仅供参考，请结合岗位实际需求与面试评估综合判断，最终决策由用人部门负责。 ',
          ),
        ),
        hrNode(
          Panel,
          { title: '十一、操作确认弹窗（删除 / 人工放行）' },
          hrNode(
            'div',
            { className: styles.confirmations },
            hrNode(Confirmation, {
              title: '删除确认',
              text: '确定要删除该候选人吗？此操作不可撤销。',
              primary: '确定删除',
              warning: true,
              onClick: () => setDialog('delete'),
            }),
            hrNode(Confirmation, {
              title: '人工放行确认',
              text: '确定要人工放行该候选人吗？放行后将进入下一流程。',
              primary: '确定放行',
              onClick: () => setDialog('release'),
            }),
          ),
        ),
        hrNode(
          Modal,
          {
            title: dialog.value === 'delete' ? '删除确认' : '人工放行确认',
            open: dialog.value !== null,
            onCancel: () => setDialog(null),
            footer: [
              hrNode(Button, { key: 'cancel', onClick: () => setDialog(null) }, ' 取消 '),
              hrNode(
                Button,
                {
                  key: 'confirm',
                  type: 'primary',
                  danger: dialog.value === 'delete',
                  onClick: () => setDialog(null),
                },
                dialog.value === 'delete' ? '确定删除' : '确定放行',
              ),
            ],
          },
          hrNode(
            Typography.Paragraph,
            null,
            dialog.value === 'delete'
              ? '确定要删除该候选人吗？此操作不可撤销。'
              : '确定要人工放行该候选人吗？放行后将进入下一流程。',
          ),
        ),
        hrNode(
          'div',
          { className: styles.footnote },
          ' 注：1. 本规范基于 1600px 页面宽度，组件在 1200px 及以上断点保持一致； ',
          hrNode('br', null),
          ' 2. 统一圆角 10px，边框 1px，颜色以本页色彩规范为准； ',
          hrNode('br', null),
          ' 3. 文字颜色使用深灰 #2F2F2F 及浅灰 #8C8C8C。 ',
        ),
      );
    };
  },
});
const Panel = defineComponent({
  name: 'Panel',
  inheritAttrs: false,
  props: Object.fromEntries(['title', 'children'].map((key) => [key, {}])) as {
    [
      K in keyof {
        title: string;
        children: VNodeChild;
      }
    ]-?: {
      type: PropType<
        {
          title: string;
          children: VNodeChild;
        }[K]
      >;
      required: true;
    };
  },
  setup(props) {
    return () => {
      const { title, children } = props;
      return hrNode('section', { className: styles.panel }, hrNode('h2', null, title), children);
    };
  },
});
const ButtonStateRow = defineComponent({
  name: 'ButtonStateRow',
  inheritAttrs: false,
  props: Object.fromEntries(['state', 'disabled'].map((key) => [key, {}])) as {
    [
      K in keyof {
        state: string;
        disabled: boolean;
      }
    ]-?: {
      type: PropType<
        {
          state: string;
          disabled: boolean;
        }[K]
      >;
      required: true;
    };
  },
  setup(props) {
    return () => {
      const { state, disabled } = props;
      return hrNode(
        Fragment,
        null,
        hrNode('span', null, state),
        hrNode(Button, { type: 'primary', disabled: disabled }, ' 生成面试题 '),
        hrNode(Button, { disabled: disabled }, '查看原始简历'),
        hrNode(Button, { type: 'link', disabled: disabled }, ' 查看原文位置 '),
      );
    };
  },
});
const StateBox = defineComponent({
  name: 'StateBox',
  inheritAttrs: false,
  props: Object.fromEntries(['title', 'children'].map((key) => [key, {}])) as {
    [
      K in keyof {
        title: string;
        children: VNodeChild;
      }
    ]-?: {
      type: PropType<
        {
          title: string;
          children: VNodeChild;
        }[K]
      >;
      required: true;
    };
  },
  setup(props) {
    return () => {
      const { title, children } = props;
      return hrNode(
        'div',
        { className: styles.stateBox },
        hrNode('strong', null, title),
        hrNode('div', null, children),
      );
    };
  },
});
const Confirmation = defineComponent({
  name: 'Confirmation',
  inheritAttrs: false,
  props: Object.fromEntries(
    ['title', 'text', 'primary', 'warning', 'onClick'].map((key) => [key, {}]),
  ) as {
    [
      K in keyof {
        title: string;
        text: string;
        primary: string;
        warning?: boolean;
        onClick: () => void;
      }
    ]-?: {
      type: PropType<
        {
          title: string;
          text: string;
          primary: string;
          warning?: boolean;
          onClick: () => void;
        }[K]
      >;
      required: true;
    };
  },
  setup(props) {
    return () => {
      const { title, text, primary, warning = false, onClick } = props;
      return hrNode(
        'div',
        { className: styles.confirmation },
        hrNode('div', null, hrNode('strong', null, title), hrNode(CloseOutlined, null)),
        hrNode(
          'p',
          null,
          hrNode(
            'span',
            { className: warning ? styles.warningText : styles.infoText },
            warning ? '⚠' : 'ⓘ',
          ),
          text,
        ),
        hrNode(
          'footer',
          null,
          hrNode(Button, { size: 'small' }, '取消'),
          hrNode(Button, { size: 'small', type: 'primary', onClick: onClick }, primary),
        ),
      );
    };
  },
});
export default HrComponentStatesPage;
</script>
