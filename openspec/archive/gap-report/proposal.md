# US-5: 技能 Gap 报告

## 概述

将 JD 分析结果（US-4 产出的 tech_stack / hard_skills / soft_skills / bonus_items）与知识库（US-3）内容做语义比对，生成三色状态报告，帮助求职者了解能力差距。

## 动机

JD 分析完成后，用户需要知道"岗位要求哪些技能、我已具备哪些、还缺什么"。Gap 报告连接 JD 分析与知识库，是 AI 简历生成（US-6）的前置依赖——只有知道 Gap 才能定向补强。

## 提议变更

### 新增端点

`POST /api/gap-report`

请求体：
```json
{
  "structured_jd": {
    "job_title": "推荐算法工程师",
    "company": "腾讯",
    "tech_stack": ["Python", "PyTorch"],
    "hard_skills": ["模型训练"],
    "soft_skills": ["跨团队协作"],
    "bonus_items": ["顶会论文"]
  }
}
```

响应体：
```json
{
  "ok": true,
  "data": {
    "overall_score": 65,
    "summary": { "covered": 2, "partial": 1, "missing": 1 },
    "items": [
      {
        "skill": "Python",
        "category": "tech_stack",
        "status": "covered",
        "score": 0.82,
        "description": "知识库中有多个 Python 项目经历记录",
        "evidence": [
          { "source_file": "work_notes.md", "chunk_text": "..." }
        ]
      }
    ]
  }
}
```

### 三色判定逻辑

对 JD 中每项技能（tech_stack + hard_skills + soft_skills + bonus_items）：
1. 调用知识库语义检索（Chroma `query`），取 top-3 结果
2. 按最高相似度分数判定状态：
   - **covered（绿）**：score ≥ 0.6
   - **partial（黄）**：0.3 ≤ score < 0.6
   - **missing（红）**：score < 0.3 或无结果
3. 调用 LLM 生成每项描述（基于命中切片真实内容，不编造）

### 前端变更

- 新增 `GapReportView` 组件：匹配度圆环 + 三色汇总 + 技能详情列表
- 集成到 `RightPanel`：JD 分析完成后自动生成 Gap 报告

## 风险

- 知识库为空时所有技能均为 missing，需提示用户先上传素材
- LLM 生成描述需严格基于检索结果，不能编造能力
- 生成延迟 ≤ 5s（含多次检索 + 1 次 LLM 调用）
