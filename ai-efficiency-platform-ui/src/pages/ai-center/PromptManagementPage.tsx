import {
  Button,
  Card,
  Empty,
  Form,
  Input,
  List,
  Select,
  Space,
  Switch,
  Typography,
  message,
} from 'antd';
import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router';

import type { PromptDefinition, PromptDetail } from '../../entities/ai-center/model';
import {
  createPromptVersion,
  getPromptVersion,
  listPrompts,
  replacePromptContent,
} from '../../features/ai-center/api';
import { promptScopeLabel } from '../../features/ai-center/presentation';
import styles from './AiCenter.module.css';

export function PromptManagementPage() {
  const [params] = useSearchParams();
  const agentId = params.get('agentId') ?? '';
  const [prompts, setPrompts] = useState<PromptDefinition[]>([]);
  const [detail, setDetail] = useState<PromptDetail>();
  const [role, setRole] = useState<'SYSTEM' | 'USER' | 'ASSISTANT'>('SYSTEM');
  const [content, setContent] = useState('');
  const [trusted, setTrusted] = useState(false);
  useEffect(() => {
    const query = new URLSearchParams(agentId ? { ownerAgentId: agentId } : {}).toString();
    void listPrompts(query)
      .then(setPrompts)
      .catch((error: Error) => message.error(error.message));
  }, [agentId]);
  const roleMessage = detail?.messages.find((item) => item.role === role);
  const showRole = (
    nextRole: 'SYSTEM' | 'USER' | 'ASSISTANT',
    nextDetail: PromptDetail | undefined = detail,
  ) => {
    const messageTemplate = nextDetail?.messages.find((item) => item.role === nextRole);
    setRole(nextRole);
    setContent(messageTemplate?.contentTemplate ?? '');
    setTrusted(messageTemplate?.trustedInstruction ?? false);
  };
  const select = async (prompt: PromptDefinition) => {
    try {
      const version = await createPromptVersion(prompt.id, {
        semanticVersion: `draft-${crypto.randomUUID()}`,
        changeSummary: '后台编辑草稿',
      });
      const nextDetail = await getPromptVersion(version.id);
      setDetail(nextDetail);
      showRole('SYSTEM', nextDetail);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '无法创建草稿');
    }
  };
  const save = async () => {
    if (!detail || detail.version.status !== 'DRAFT') return;
    const other = detail.messages
      .filter((item) => item.role !== role)
      .map((item) => ({
        ordinal: item.ordinal,
        role: item.role,
        messageKey: item.messageKey,
        contentTemplate: item.contentTemplate,
        trustedInstruction: item.trustedInstruction,
      }));
    const current = {
      ordinal: roleMessage?.ordinal ?? detail.messages.length + 1,
      role,
      messageKey: roleMessage?.messageKey ?? role.toLowerCase(),
      contentTemplate: content,
      trustedInstruction: trusted,
    };
    try {
      await replacePromptContent(detail.version.id, {
        messages: [...other, current].sort((a, b) => a.ordinal - b.ordinal),
        variables: detail.variables.map((item) => ({
          messageKey:
            detail.messages.find((messageItem) => messageItem.id === item.promptMessageTemplateId)
              ?.messageKey ?? '',
          variableName: item.variableName,
          valueType: item.valueType,
          valueSource: item.valueSource,
          required: item.required,
          sensitive: item.sensitive,
          maxLength: item.maxLength,
          allowUntrustedContent: item.allowUntrustedContent,
        })),
      });
      setDetail(await getPromptVersion(detail.version.id));
      message.success('Prompt 草稿已保存');
    } catch (error) {
      message.error(error instanceof Error ? error.message : '保存失败');
    }
  };
  return (
    <section className={styles.page}>
      <header>
        <Typography.Title level={2}>Prompt 管理</Typography.Title>
        <Typography.Text type="secondary">
          共享 Prompt 与 Agent 私有 Prompt 分开归属，正文按消息角色编辑。
        </Typography.Text>
      </header>
      <div className={styles.threeColumns}>
        <Card className={styles.panel} title="Prompt 资产">
          <List
            className={styles.promptAssetList}
            dataSource={prompts}
            locale={{ emptyText: '暂无 Prompt' }}
            renderItem={(item) => (
              <List.Item
                actions={[
                  <Button key="edit" type="link" onClick={() => void select(item)}>
                    创建草稿并编辑
                  </Button>,
                ]}
              >
                <List.Item.Meta
                  title={item.name}
                  description={`${promptScopeLabel(item.scope)} · ${item.stageKey}`}
                />
              </List.Item>
            )}
          />
        </Card>
        <Card
          className={styles.panel}
          title={
            detail ? `${detail.definition.name} · ${detail.version.semanticVersion}` : '消息编辑器'
          }
        >
          {detail ? (
            <Space direction="vertical" size={16} style={{ width: '100%' }}>
              <Select
                value={role}
                onChange={(value) => showRole(value)}
                options={[
                  { value: 'SYSTEM', label: '系统提示词（SYSTEM）' },
                  { value: 'USER', label: '用户提示词（USER）' },
                  { value: 'ASSISTANT', label: '助手消息（ASSISTANT）' },
                ]}
              />
              <Input.TextArea
                rows={18}
                value={content}
                onChange={(event) => setContent(event.target.value)}
                readOnly={detail.version.status !== 'DRAFT'}
              />
              <Space>
                <Switch
                  checked={trusted}
                  onChange={setTrusted}
                  disabled={detail.version.status !== 'DRAFT'}
                />
                可信指令
                <Button
                  type="primary"
                  disabled={detail.version.status !== 'DRAFT'}
                  onClick={() => void save()}
                >
                  保存草稿
                </Button>
              </Space>
            </Space>
          ) : (
            <Empty description="选择 Prompt 后创建独立草稿版本" />
          )}
        </Card>
        <Card className={styles.panel} title="变量契约">
          {detail ? (
            <Form layout="vertical">
              {detail.variables.map((item) => (
                <Form.Item key={item.id} label={item.variableName} required={item.required}>
                  <Input
                    value={`${item.valueType} / ${item.valueSource}${item.sensitive ? ' / 敏感' : ''}`}
                    readOnly
                  />
                </Form.Item>
              ))}
            </Form>
          ) : (
            <Empty description="暂无变量" />
          )}
        </Card>
      </div>
    </section>
  );
}
