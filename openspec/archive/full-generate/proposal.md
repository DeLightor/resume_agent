# US-14: 一键生成整份简历

## 概述

新增 `POST /api/generate/full` 端点，并行调用各段落生成（asyncio.gather），生成完整简历。自我评价用 AI 生成，其他段落（experience/projects/skills）从知识库检索素材生成。个人信息从节点 `personal_info` 带入，不需要 AI 生成。支持单段重新生成。

## 提议变更

### 后端

**1. 新增 `POST /generate/full` 端点**

- 请求体：`{ node_id, structured_jd?, gap_report? }`
- 并行生成 4 个段落：summary（AI 生成）+ experience + projects + skills
- 个人信息从节点 `personal_info` 读取，不生成
- 有素材的段落生成内容，无素材的留空并标注
- 生成结果写入节点 `content_json`（合并已有数据）
- 返回完整简历数据

**2. 新增 `POST /generate/section` 端点（单段重新生成）**

- 请求体：`{ node_id, section, structured_jd?, gap_report? }`
- 只重新生成指定段落，不影响其他段落
- 生成后更新节点 `content_json` 中对应段落

**3. summary 段落生成**

- 新增 `_WRITER_PROMPT_SUMMARY` 系统提示
- LLM 基于知识库素材 + JD 生成 2-3 句自我评价

### 前端

**1. 一键生成按钮**

- 中栏编辑器 Tab 工具栏新增"一键生成"按钮
- 点击后调用 `POST /generate/full`
- 生成中显示 loading 状态
- 生成完自动填充预览区

**2. 单段重新生成**

- 预览区每个段落标题旁新增"重新生成"图标按钮
- 点击后调用 `POST /generate/section`
- 只更新对应段落，不影响其他段落

## 约束

- 不引入新依赖
- 复用现有 generate.py 的检索/反思/撰写逻辑
- 个人信息不参与 AI 生成
- 生成结果存入节点 content_json
