# US-6: AI 动态生成简历

## 概述

基于 JD 分析结果（US-4）和 Gap 报告（US-5），结合知识库中的真实经历，AI 生成定制化简历内容。工作流：检索相关经历 → 反思审核（检测套话/夸大） → 撰写润色。

## 动机

Gap 报告告诉用户"缺什么"，但用户还需要"怎么写"。US-6 解决最后一步：把知识库中的真实经历，按 JD 要求定向组织成简历段落，避免海投通用简历。

## 提议变更

### 新增端点

`POST /api/generate`

请求体：
```json
{
  "structured_jd": { "job_title": "...", "tech_stack": [...], ... },
  "gap_report": { "items": [...], "summary": {...} },
  "section": "experience"
}
```

响应体：
```json
{
  "ok": true,
  "data": {
    "section": "experience",
    "content": {
      "experience": [
        {
          "company": "...",
          "role": "...",
          "period": "...",
          "highlights": ["...", "..."]
        }
      ]
    },
    "reflection": {
      "issues_found": 0,
      "notes": "内容均基于知识库真实记录，无套话或夸大表述"
    },
    "sources_used": 3
  }
}
```

### 工作流（3 步，不引入 LangGraph 依赖）

1. **检索**：对 JD 中每项技能（tech_stack + hard_skills），在知识库中检索 top-3 经历切片，合并去重
2. **反思**：LLM 审核检索到的内容，检测套话、前后矛盾、夸大表述，输出 issues 列表
3. **撰写**：LLM 基于检索内容 + 反思结果，生成目标段落（experience / projects / skills）

### 前端变更

- 新增 `GenerateView` 组件：段落选择（经历/项目/技能）+ 生成按钮 + 结果展示 + 反思提示
- 集成到 `RightPanel` 第 3 区（替换空状态提示）

## 约束

- 不引入 LangGraph 或其他新依赖
- 生成内容必须基于知识库真实记录，反思节点检测套话/夸大
- 不承诺验证经历真实性（只检测表述质量）
- 生成延迟 ≤ 20s（含 2 次 LLM 调用）
- 生成结果可编辑修正
