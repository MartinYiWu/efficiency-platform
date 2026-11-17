import { h, isVNode, Fragment, type Component, type VNode, type VNodeChild } from 'vue';
import {
  Alert,
  Button,
  Table,
  Tabs,
  TabPane,
  Collapse,
  CollapsePanel,
  Dropdown,
  Menu,
  MenuItem,
  MenuDivider,
  Descriptions,
  DescriptionsItem,
} from 'ant-design-vue';
type Item = {
  key?: string;
  type?: string;
  label?: VNodeChild;
  children?: VNodeChild;
  disabled?: boolean;
  danger?: boolean;
  span?: number;
};
type Column = {
  render?: (text: unknown, record: unknown, index: number) => VNodeChild;
  [key: string]: unknown;
};
type MenuOptions = { items: Item[]; onClick?: (event: { key: string }) => void };
/** HR render 页面的 Ant Design Vue 插槽与复合控件构建。 */
export function v(
  type: Component | string | symbol | typeof Fragment,
  input: object | null,
  ...children: VNodeChild[]
): VNode {
  const props: Record<string, unknown> = { ...(input || {}) };
  if (type === Alert && props.title) {
    props.message = props.title;
    delete props.title;
  }
  if (props.className !== undefined) {
    props.class = props.className;
    delete props.className;
  }
  if (props.htmlFor !== undefined) {
    props.for = props.htmlFor;
    delete props.htmlFor;
  }
  const flat = (children as unknown[])
    .flat(Infinity)
    .filter(
      (child) => child !== null && child !== undefined && child !== false && child !== true,
    ) as VNodeChild[];
  if (
    type === Button &&
    props['aria-label'] === undefined &&
    flat.every((child) => typeof child === 'string')
  ) {
    const label = flat.join('').trim();
    if (/^[\u4e00-\u9fff]{2}$/.test(label)) props['aria-label'] = label;
  }
  if (typeof type === 'string' || type === Fragment) {
    if (props.onChange && ['input', 'textarea'].includes(String(type))) {
      props.onInput = props.onChange;
      delete props.onChange;
    }
    return h(type as string, props, flat);
  }
  const slots: Record<string, () => VNodeChild> = {};
  if (flat.length) slots.default = () => flat;
  for (const key of ['icon', 'prefix', 'suffix', 'extra', 'title', 'footer', 'description']) {
    if (isVNode(props[key]) || Array.isArray(props[key])) {
      const content = props[key] as VNodeChild;
      slots[key] = () => content;
      delete props[key];
    }
  }
  if (type === Table && props.columns)
    props.columns = (props.columns as Column[]).map(({ render, ...column }) =>
      render
        ? {
            ...column,
            customRender: ({
              text,
              record,
              index,
            }: {
              text: unknown;
              record: unknown;
              index: number;
            }) => render(text, record, index),
          }
        : column,
    );
  if ((type === Tabs || type === Collapse || type === Descriptions) && props.items) {
    const items = props.items as Item[];
    delete props.items;
    slots.default = () =>
      items.map((item) =>
        type === Tabs
          ? h(
              TabPane,
              { key: item.key, tab: item.label, disabled: item.disabled },
              { default: () => item.children },
            )
          : type === Collapse
            ? h(
                CollapsePanel,
                { key: item.key, header: item.label },
                { default: () => item.children },
              )
            : h(
                DescriptionsItem,
                { key: item.key, label: item.label, span: item.span },
                { default: () => item.children },
              ),
      );
  }
  if (type === Dropdown && props.menu) {
    const menu = props.menu as MenuOptions;
    delete props.menu;
    slots.overlay = () =>
      h(
        Menu,
        { onClick: (event) => menu.onClick?.({ key: String(event.key) }) },
        {
          default: () =>
            menu.items.map((item) =>
              item.type === 'divider'
                ? h(MenuDivider)
                : h(
                    MenuItem,
                    { key: item.key, danger: item.danger, disabled: item.disabled },
                    { default: () => item.label },
                  ),
            ),
        },
      );
  }
  if (typeof type === 'object' && type.props && 'children' in type.props) props.children = flat;
  return h(type as Component, props, slots);
}
