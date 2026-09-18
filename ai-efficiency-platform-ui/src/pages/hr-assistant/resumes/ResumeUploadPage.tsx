import {
  CloudUploadOutlined,
  DeleteOutlined,
  FileImageOutlined,
  FilePdfOutlined,
  FileTextOutlined,
  FileWordOutlined,
  FileZipOutlined,
  InfoCircleFilled,
  UserOutlined,
} from '@ant-design/icons';
import {
  Button,
  Checkbox,
  Collapse,
  Input,
  Modal,
  Select,
  Switch,
  Tabs,
  Tooltip,
  Typography,
  message,
} from 'antd';
import { useRef, useState, type ChangeEvent, type DragEvent } from 'react';
import { useNavigate } from 'react-router';

import styles from './ResumeUploadPage.module.css';

type UploadStatus = 'pending' | 'image' | 'invalid' | 'duplicate';
type UploadFile = {
  id: string;
  name: string;
  size: string;
  status: UploadStatus;
  nestedCount?: number;
  detail?: string;
};

const initialFiles: UploadFile[] = [
  { id: 'zhang-wei', name: '张伟_后端开发工程师.pdf', size: '1.24 MB', status: 'pending' },
  { id: 'li-jing', name: '李静_后端开发工程师.docx', size: '892 KB', status: 'pending' },
  { id: 'wang-yuan', name: '王远_后端开发工程师.txt', size: '318 KB', status: 'pending' },
  {
    id: 'resume-package',
    name: '应届生简历合集.zip',
    size: '18.6 MB',
    status: 'pending',
    nestedCount: 12,
  },
  {
    id: 'liu-min',
    name: '刘小怡_后端开发工程师.jpg',
    size: '1.05 MB',
    status: 'image',
    detail: '图片型简历，OCR 识别中',
  },
  {
    id: 'chen-hao',
    name: '陈小然_后端开发工程师.pdf',
    size: '1.12 MB',
    status: 'invalid',
    detail: '格式异常：文件已加密，无法解析',
  },
  { id: 'zhao-yi', name: '赵小涵_后端开发工程师.docx', size: '1.01 MB', status: 'pending' },
  {
    id: 'zhou-ming',
    name: '周小明_后端开发工程师.docx',
    size: '956 KB',
    status: 'duplicate',
    detail: '疑似重复：与现有简历相似度较高',
  },
];

const acceptedExtensions = new Set([
  'pdf',
  'doc',
  'docx',
  'jpg',
  'jpeg',
  'png',
  'txt',
  'md',
  'html',
  'zip',
  'rar',
  '7z',
]);

function getExtension(fileName: string) {
  return fileName.split('.').pop()?.toLowerCase() ?? '';
}

function formatSize(size: number) {
  if (size < 1024 * 1024) return `${Math.max(1, Math.round(size / 1024))} KB`;
  return `${(size / (1024 * 1024)).toFixed(2)} MB`;
}

function createUploadFile(file: File): UploadFile {
  const extension = getExtension(file.name);
  const isArchive = ['zip', 'rar', '7z'].includes(extension);
  const maximumSize = isArchive ? 100 * 1024 * 1024 : 20 * 1024 * 1024;
  const isImage = ['jpg', 'jpeg', 'png'].includes(extension);

  if (!acceptedExtensions.has(extension) || file.size > maximumSize) {
    return {
      id: `${file.name}-${file.lastModified}`,
      name: file.name,
      size: formatSize(file.size),
      status: 'invalid',
      detail: !acceptedExtensions.has(extension)
        ? '格式异常：不支持该文件格式'
        : `格式异常：${isArchive ? '压缩包' : '单个文件'}超过大小限制`,
    };
  }

  return {
    id: `${file.name}-${file.lastModified}`,
    name: file.name,
    size: formatSize(file.size),
    status: isImage ? 'image' : 'pending',
    detail: isImage ? '图片型简历，OCR 识别中' : undefined,
  };
}

function FileIcon({ file }: { file: UploadFile }) {
  const extension = getExtension(file.name);
  if (extension === 'pdf') return <FilePdfOutlined className={styles.pdfIcon} />;
  if (['doc', 'docx'].includes(extension)) return <FileWordOutlined className={styles.wordIcon} />;
  if (['zip', 'rar', '7z'].includes(extension))
    return <FileZipOutlined className={styles.zipIcon} />;
  if (['jpg', 'jpeg', 'png'].includes(extension))
    return <FileImageOutlined className={styles.imageIcon} />;
  return <FileTextOutlined className={styles.textIcon} />;
}

function StatusLabel({ file }: { file: UploadFile }) {
  const className =
    file.status === 'image'
      ? styles.imageStatus
      : file.status === 'invalid'
        ? styles.invalidStatus
        : file.status === 'duplicate'
          ? styles.duplicateStatus
          : styles.pendingStatus;
  const text =
    file.status === 'pending'
      ? file.nestedCount
        ? `等待上传 · 含 ${file.nestedCount} 个文件`
        : '等待上传'
      : file.detail;

  return <span className={className}>{text}</span>;
}

export function ResumeUploadPage() {
  const navigate = useNavigate();
  const [notice, context] = message.useMessage();
  const [activeTab, setActiveTab] = useState('file');
  const [consent, setConsent] = useState(true);
  const [onlyStore, setOnlyStore] = useState(false);
  const [files, setFiles] = useState(initialFiles);
  const [textResume, setTextResume] = useState('');
  const [selectedCandidates, setSelectedCandidates] = useState<string[]>([]);
  const [consentOpen, setConsentOpen] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const totalResumes = files.reduce((total, file) => total + (file.nestedCount ?? 1), 0);
  const canSubmit =
    consent &&
    ((activeTab === 'file' && files.length > 0) ||
      (activeTab === 'text' && textResume.trim().length > 0) ||
      (activeTab === 'library' && selectedCandidates.length > 0));

  const addFiles = (incomingFiles: FileList | File[]) => {
    const createdFiles = Array.from(incomingFiles).map(createUploadFile);
    if (files.length + createdFiles.length > 100) {
      notice.error('单次最多上传 100 份简历，请先移除部分文件');
      return;
    }
    setFiles((current) => [...current, ...createdFiles]);
  };
  const handleFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    if (event.target.files) addFiles(event.target.files);
    event.target.value = '';
  };
  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    if (event.dataTransfer.files.length > 0) addFiles(event.dataTransfer.files);
  };
  const handleStart = () => {
    if (!consent) return;
    notice.success('已创建解析批次 20260901-001，文件将按上传顺序进入解析队列');
    navigate('/ai-assistants/hr/resumes/batches/20260901-001');
  };

  const tabItems = [
    {
      key: 'file',
      label: '文件上传',
      children: (
        <div className={styles.fileTab}>
          <div
            className={styles.dropZone}
            onDragOver={(event) => event.preventDefault()}
            onDrop={handleDrop}
          >
            <CloudUploadOutlined />
            <strong>拖拽文件到此处，或点击选择</strong>
            <span>支持 PDF、DOC、DOCX、TXT、ZIP、RAR，单个文件 ≤ 20MB，压缩包 ≤ 100MB</span>
            <Button type="primary" onClick={() => fileInputRef.current?.click()}>
              选择文件
            </Button>
            <input
              ref={fileInputRef}
              className={styles.hiddenInput}
              type="file"
              multiple
              accept=".pdf,.doc,.docx,.jpg,.jpeg,.png,.txt,.md,.html,.zip,.rar,.7z"
              aria-label="选择简历文件"
              onChange={handleFileChange}
            />
          </div>
          <div className={styles.selectedSummary}>
            <span>
              已选择 {files.length} 个文件（共 {totalResumes} 份）
            </span>
          </div>
          <div className={styles.fileList} aria-label="已选简历文件">
            {files.map((file) => (
              <div key={file.id} className={styles.fileRow}>
                <FileIcon file={file} />
                <span className={styles.fileName}>{file.name}</span>
                <span className={styles.fileSize}>{file.size}</span>
                <StatusLabel file={file} />
                <Button
                  type="link"
                  icon={<DeleteOutlined />}
                  aria-label={`移除 ${file.name}`}
                  onClick={() =>
                    setFiles((current) => current.filter((item) => item.id !== file.id))
                  }
                >
                  移除
                </Button>
              </div>
            ))}
          </div>
        </div>
      ),
    },
    {
      key: 'text',
      label: '粘贴文本',
      children: (
        <div className={styles.textTab}>
          <Input.TextArea
            rows={12}
            value={textResume}
            maxLength={50000}
            placeholder="粘贴简历文本内容。适用于从邮件、聊天工具复制的简历。"
            onChange={(event) => setTextResume(event.target.value)}
          />
          <span className={styles.characterCount}>{textResume.length} / 50000</span>
          {textResume.length > 0 && textResume.length < 200 && (
            <span className={styles.lowContentWarning}>内容过少，可能无法提取有效信息</span>
          )}
          <Input placeholder="候选人姓名（选填，留空则从内容中自动识别）" />
        </div>
      ),
    },
    {
      key: 'library',
      label: '从人才库选择',
      children: (
        <div className={styles.libraryTab}>
          <div className={styles.specCompletion}>
            <InfoCircleFilled />
            <span>规格补全：选择已入库候选人后，会按当前解析设置重新处理。</span>
          </div>
          <Typography.Text type="secondary">选择需要补充到本次处理批次的候选人</Typography.Text>
          {[
            ['candidate-1', '赵磊', '后端开发工程师 · 5年 · 上海'],
            ['candidate-2', '孙芳', 'Java 工程师 · 4年 · 杭州'],
            ['candidate-3', '吴磊', '后端开发工程师 · 6年 · 上海'],
          ].map(([id, name, summary]) => (
            <Checkbox
              key={id}
              checked={selectedCandidates.includes(id)}
              onChange={(event) =>
                setSelectedCandidates((current) =>
                  event.target.checked
                    ? [...current, id]
                    : current.filter((candidateId) => candidateId !== id),
                )
              }
            >
              <span className={styles.candidateOption}>
                <UserOutlined />
                <span>
                  <strong>{name}</strong>
                  <small>{summary}</small>
                </span>
              </span>
            </Checkbox>
          ))}
        </div>
      ),
    },
  ];

  return (
    <div className={styles.page}>
      {context}
      <header className={styles.heading}>
        <div>
          <Typography.Title level={1}>上传简历</Typography.Title>
          <Typography.Text>
            支持单份、批量、压缩包与文本粘贴。上传后自动解析并与指定岗位匹配。
          </Typography.Text>
        </div>
        <div className={styles.aiNotice}>
          <InfoCircleFilled />
          <span>AI 仅辅助解析，请结合人工核对使用。</span>
        </div>
      </header>

      <section className={styles.contentGrid} aria-label="简历上传工作区">
        <aside className={styles.settingsPanel} aria-label="上传配置">
          <section className={styles.settingSection}>
            <Typography.Title level={2}>目标岗位（必填）</Typography.Title>
            <Select
              value={onlyStore ? undefined : 'backend'}
              placeholder={onlyStore ? '仅入库，不自动匹配' : undefined}
              disabled={onlyStore}
              options={[{ value: 'backend', label: '后端开发工程师（P6）' }]}
              aria-label="目标岗位"
            />
            <div className={styles.matchHint}>
              <Typography.Text type="secondary">
                {onlyStore
                  ? '解析完成后将进入人才库，不会自动匹配岗位'
                  : '解析完成后将自动与该岗位匹配'}
              </Typography.Text>
              <Button
                type="link"
                className={styles.storeOnlyLink}
                onClick={() => setOnlyStore((value) => !value)}
              >
                {onlyStore ? '恢复指定岗位匹配' : '暂不匹配，仅入库'}
              </Button>
            </div>
          </section>

          <section className={styles.configurationSummary}>
            <Typography.Title level={2}>当前配置概览</Typography.Title>
            <dl>
              <div>
                <dt>硬性条件</dt>
                <dd>4 条</dd>
              </div>
              <div>
                <dt>核心技能</dt>
                <dd>5 项</dd>
              </div>
              <div>
                <dt>权重分配</dt>
                <dd>技能 40% / 经验 25% / 项目 25% / 学历 5% / 加分 5%</dd>
              </div>
            </dl>
            <Button type="link" onClick={() => navigate('/ai-assistants/hr/positions/backend')}>
              查看完整配置
            </Button>
          </section>

          <Collapse
            className={styles.switchSection}
            items={[
              {
                key: 'processing-settings',
                label: '处理设置',
                children: (
                  <div className={styles.switchList}>
                    <SettingSwitch title="低置信度简历人工确认" description="低于阈值转人工确认" />
                    <SettingSwitch title="自动去重" description="自动合并重复简历" />
                    <SettingSwitch title="自动存入人才库" description="完成匹配后自动入库" />
                  </div>
                ),
              },
            ]}
          />

          <section className={styles.consentPanel}>
            <Checkbox checked={consent} onChange={(event) => setConsent(event.target.checked)}>
              已获得候选人授权，可用于本次招聘评估
            </Checkbox>
            <Typography.Text>上传前请确认已取得候选人同意。</Typography.Text>
            <Button type="link" onClick={() => setConsentOpen(true)}>
              查看告知同意说明
            </Button>
          </section>
        </aside>

        <section className={styles.uploadPanel} aria-label="上传方式">
          <Tabs activeKey={activeTab} items={tabItems} onChange={setActiveTab} />
        </section>
      </section>

      <footer className={styles.footerBar} aria-label="上传操作">
        <span>
          <InfoCircleFilled /> 上传后可在解析进度页查看处理情况
        </span>
        <div>
          <Button onClick={() => navigate('/ai-assistants/hr/workbench')}>取消</Button>
          <Tooltip title={consent ? undefined : '请先确认候选人授权'}>
            <span>
              <Button type="primary" disabled={!canSubmit} onClick={handleStart}>
                开始上传并解析
              </Button>
            </span>
          </Tooltip>
        </div>
      </footer>

      <Modal
        title="候选人授权与告知说明"
        open={consentOpen}
        footer={null}
        onCancel={() => setConsentOpen(false)}
      >
        <Typography.Paragraph>
          候选人简历仅用于本次招聘评估与人才库管理，请在处理前确认已取得候选人同意。
        </Typography.Paragraph>
        <Typography.Paragraph>
          档案保留期限、处理方式与删除请求将遵循平台的全局规则配置。
        </Typography.Paragraph>
        <Button type="primary" onClick={() => setConsentOpen(false)}>
          我已了解
        </Button>
      </Modal>
    </div>
  );
}

function SettingSwitch({ title, description }: { title: string; description: string }) {
  const [enabled, setEnabled] = useState(true);
  return (
    <div className={styles.switchRow}>
      <div>
        <strong>{title}</strong>
        <span>{description}</span>
      </div>
      <Switch checked={enabled} onChange={setEnabled} aria-label={title} />
    </div>
  );
}
