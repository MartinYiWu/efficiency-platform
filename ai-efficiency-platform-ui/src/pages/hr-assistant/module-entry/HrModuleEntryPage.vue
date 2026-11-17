<script lang="ts">
import { defineComponent, type PropType } from 'vue';
import { v as hrNode } from '../hrVnodes';
import { AppstoreOutlined } from '@ant-design/icons-vue';
import { Card, Typography } from 'ant-design-vue';
import styles from './HrModuleEntryPage.module.css';
export const HrModuleEntryPage = defineComponent({
  name: 'HrModuleEntryPage',
  inheritAttrs: false,
  props: Object.fromEntries(['title', 'description', 'nextPage'].map((key) => [key, {}])) as {
    [
      K in keyof {
        title: string;
        description: string;
        nextPage: string;
      }
    ]-?: {
      type: PropType<
        {
          title: string;
          description: string;
          nextPage: string;
        }[K]
      >;
      required: true;
    };
  },
  setup(props) {
    return () => {
      const { title, description, nextPage } = props;
      return hrNode(
        'div',
        { className: [styles.page, 'ui-page'] },
        hrNode(
          'p',
          { className: styles.demoNotice, role: 'note' },
          ' 演示数据 · 当前页面展示前端示例，非真实招聘结果。 ',
        ),
        hrNode(Typography.Title, { level: 1 }, title),
        hrNode(Typography.Text, { type: 'secondary' }, description),
        hrNode(
          Card,
          { className: styles.card },
          hrNode(AppstoreOutlined, null),
          hrNode(Typography.Title, { level: 2 }, title, '页面准备中'),
          hrNode(
            Typography.Paragraph,
            null,
            ' 该模块将严格按照 UI 设计稿逐页接入。下一张计划开发页面：',
            nextPage,
            '。 ',
          ),
        ),
      );
    };
  },
});
export default HrModuleEntryPage;
</script>
