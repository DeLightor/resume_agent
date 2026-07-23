# Design: asset-cold-start

## 1. 架构概览

```
用户拖入文件
    │
    ▼
POST /api/resumes/upload ──→ 保存文件到 disk ──→ 创建 upload_records 记录
    │
    ▼
POST /api/resumes/parse
    │
    ├── 1. 读取文件，提取纯文本（PDF: PyMuPDF / Word: python-docx）
    ├── 2. LLM 结构化提取（text → JSON: basic/education/experience/projects/skills/direction）
    ├── 3. 去重检查（company + direction 是否已存在节点）
    ├── 4. 生成版本树节点（Master → branch → company）
    └── 5. 更新 upload_records.parse_status = success
    │
    ▼
返回 { structured_resume, tree_node }
```

## 2. 新增模块设计

### 2.1 LLM Client（`llm/client.py`）

统一 LLM 调用层，基于 `openai` Python SDK，通过 `base_url` 支持多提供商。

```python
class LLMClient:
    """统一 LLM 客户端，支持 OpenAI / DeepSeek / 自定义。"""
    
    def __init__(self, provider, api_key, base_url, model="gpt-4o"):
        # openai SDK 的 base_url 参数支持 DeepSeek 和自定义端点
        # Claude 通过 Anthropic OpenAI-compatible 端点支持
        
    async def chat(self, system_prompt, user_content, response_format_json=False) -> str:
        """发送 chat completion 请求。"""
```

**设计决策**：用 `openai` SDK 而非 `anthropic` SDK。原因：
- OpenAI SDK 通过 `base_url` 参数兼容 DeepSeek、Moonshot、本地 Ollama 等
- Anthropic 已提供 OpenAI-compatible 端点
- 一个 SDK 覆盖所有提供商，减少依赖

### 2.2 文件解析器（`parsers/`）

```python
# parsers/pdf_parser.py
def extract_text_from_pdf(file_path: Path) -> str:
    """用 PyMuPDF 提取 PDF 全文。按页拼接，页间用 \\n\\n 分隔。"""

# parsers/docx_parser.py
def extract_text_from_docx(file_path: Path) -> str:
    """用 python-docx 提取 Word 全文。遍历段落 + 表格单元格。"""
```

### 2.3 结构化提取器（`parsers/extractor.py`）

```python
class ResumeExtractor:
    """用 LLM 从简历纯文本提取结构化数据。"""
    
    async def extract(self, raw_text: str) -> StructuredResume:
        """提取结构化简历数据。
        
        Returns:
            StructuredResume:
                basic: {name, phone, email, location}
                education: [{school, degree, major, period}]
                experience: [{company, role, period, highlights[]}]
                projects: [{name, role, description}]
                skills: [str]
                primary_direction: str  # 推断的方向（安全/算法/后端/前端/数据/产品/其他）
        """
```

**Prompt 设计要点**：
- System prompt 明确角色：「你是简历解析专家」
- 要求输出 JSON，字段固定
- 明确禁止编造：找不到的字段返回 null 或空数组
- 要求推断 `primary_direction`：基于技能和经历关键词匹配

### 2.4 版本树生成（`services/tree_builder.py`）

```python
class TreeBuilder:
    """根据结构化简历数据生成版本树节点。"""
    
    def build_from_resume(self, resume: StructuredResume) -> TreeNode:
        """创建或更新版本树节点。
        
        逻辑：
        1. 确保 Master 节点存在（init_db 已 seed）
        2. 查找 primary_direction 对应的 branch 节点
           - 不存在 → 创建 branch（parent_id=master, direction=primary_direction）
        3. 查找同方向的 company 节点（company 字段匹配）
           - 存在 → 更新 content_json（去重，保留最新版）
           - 不存在 → 创建 company 节点（parent_id=branch_id, content_json=resume_json）
        """
```

## 3. API 端点设计

### 3.1 POST /api/resumes/upload
- **Input**: `UploadFile`（multipart/form-data）
- **验证**: 文件扩展名 ∈ {pdf, docx}
- **操作**: 保存到 `{files_root}/resumes/{uuid}.{ext}`，写入 `upload_records` 表
- **Output**: `{upload_id, file_name, file_type, parse_status: "pending"}`

### 3.2 POST /api/resumes/parse
- **Input**: `{upload_id: str}`
- **操作**:
  1. 从 DB 获取 upload_record
  2. 根据文件类型调用解析器提取文本
  3. 调用 LLM 提取结构化数据
  4. 调用 TreeBuilder 创建/更新版本树节点
  5. 更新 upload_record.parse_status
- **Output**: `{structured_resume, tree_node, deduplicated: bool}`
- **错误处理**: LLM 调用失败 → parse_status="needs_review"，保留原始文本

### 3.3 GET /api/resumes/list
- **Output**: `[{id, file_name, file_type, parse_status, created_at}]`

### 3.4 GET /api/tree（改造）
- 从 mock 数据改为从 `resume_versions` 表读取
- 构建 nodes + edges 返回

## 4. 数据流

```
UploadFile → save to disk → upload_records(pending)
                                    ↓
                            extract_text (PDF/Word)
                                    ↓
                            LLM extract → StructuredResume JSON
                                    ↓
                            TreeBuilder.build_from_resume()
                            ├── find or create branch node
                            └── find or create/update company node
                                    ↓
                            upload_records(success)
```

## 5. 前端改动

### 5.1 UploadZone 增强
- 添加隐藏 `<input type="file" accept=".pdf,.docx">`
- 拖拽事件处理（dragover, drop）
- 调用 `POST /api/resumes/upload`，然后 `POST /api/resumes/parse`
- 显示上传中/解析中/完成/失败状态

### 5.2 VersionTree 接 API
- 从 `GET /api/tree` 获取数据
- 替换 `mockTree.ts` 的静态导入

### 5.3 API 层
- `lib/api.ts` 新增 `uploadResume(file)`, `parseResume(uploadId)`, `getTree()`

## 6. 测试策略

| 测试项 | 类型 | 方法 |
|--------|------|------|
| PDF 解析器 | 单元 | 创建测试 PDF → 提取文本 → 验证内容 |
| Word 解析器 | 单元 | 创建测试 DOCX → 提取文本 → 验证内容 |
| LLM 提取器 | 单元 | Mock LLMClient → 验证 JSON 解析 |
| TreeBuilder | 单元 | 空 DB → 创建 branch → 创建 company → 去重更新 |
| API upload | 集成 | TestClient 上传文件 → 验证响应 + DB 记录 |
| API parse | 集成 | Mock LLM → 验证完整流程 |
| API tree | 集成 | 插入节点 → GET /api/tree → 验证结构 |
