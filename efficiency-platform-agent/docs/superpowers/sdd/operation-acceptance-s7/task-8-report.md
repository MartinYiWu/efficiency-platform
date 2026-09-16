# S7 Task 8 实施报告：固定 Fixture 生成治理（阶段性）

本轮完成确定性 Fixture 生成器、文档预检、Docling 本地文件适配器、延迟初始化的本地 PaddleOCR 适配器、DocumentIngestionService 薄服务、带 `run_id`/`X-Tenant-ID`/大小上限的 `/v1/runs/{run_id}/files` 上传 API，以及实现 S5 `AnalyticsFileReader.open()` 端口的只读 Polars Reader。预检在解析器/Artifact 前拒绝危险文件名、大小超限、扩展名/MIME 不一致和容器签名不匹配；服务拒绝状态不索引、同一 upload_id 不重复解析并始终清理临时目录。PaddleOCR 仅接受显式本地模型目录，目录不存在或目录为空时失败关闭，不触发自动下载。

默认路径对 PDF 失败关闭，不初始化 Docling PDF 管线；只有调用方显式注入本地 PDF 管线时才允许解析，扫描件必须转入显式本地 PaddleOCR 适配器，避免默认路径触发模型下载。

`DocumentIngestionService` 仅在解析和索引均成功后登记 `upload_id`；失败请求不会污染去重集合，可使用相同标识安全重试。

`create_app` 已支持通过 `document_service` 显式注入并挂载上传路由；未注入时不创建文档服务或外部依赖，保持默认应用无副作用。

已在 `tests/fixtures/s7` 生成 12 个固定样本及 manifest；DOCX/XLSX/PDF/PNG/Parquet 样本具有对应容器签名，manifest 的 SHA-256 与实际文件内容一致，并记录预期结构。临时目录双次同 seed 一致性、四格式 Polars 读取、文档预检、摄取、OCR、上传 API 和上传链相关测试通过。Ruff、format、Python 3.13 语法编译通过。

补充验证：使用仓库合成 Markdown 样本执行真实 Docling 本地转换，结果包含预期文本；PaddleOCR 本地模型未加载，未构造真实 OCR 模型、用户文件或网络连接。OCR 召回率、复杂 PDF/Office 质量和生产上传验收仍未验证，不能据此宣称真实质量或生产可用。

Docling 验证命令：`uv run python -c "from pathlib import Path; from docling.document_converter import DocumentConverter; result=DocumentConverter().convert(Path('tests/fixtures/s7/plain_text_v1.md')); print('docling-local-markdown-ok', '青禾实验室' in result.document.export_to_markdown())"`，输出 `docling-local-markdown-ok True`。

## 边界事件记录

对合成 PDF 做本地 Docling 深度转换时，默认依赖链自动尝试从 ModelScope 下载 RapidOCR 模型。该行为不符合本阶段真实 Gate 默认关闭约束；进程已停止，新增的四个模型文件已从本地虚拟环境精确移除。后续 PDF/OCR 验收必须显式提供本地模型目录或使用拒绝网络的 Stub，不能直接调用默认转换器。
