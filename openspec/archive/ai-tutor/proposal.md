# US-11: AI 导师学习建议

## 概述

基于 Gap 报告中"未涉及"和"部分缺口"的技能项，调用 LLM 生成学习路径建议（概念→实践→验证），推荐学习资源（文档/课程/开源项目/面试题），并支持标记学习状态（已掌握/学习中/待开始）。

## 动机

求职者通过 Gap 报告发现技能缺口后，不知道该学什么、怎么学、去哪找资源。AI 导师基于具体缺口生成结构化学习路径，帮助求职者在面试前高效补齐短板。

## 提议变更

### 后端：新增 Tutor 端点

`POST /api/tutor/suggest`

请求体：
```json
{
  "items": [
    { "skill": "Kubernetes", "category": "tech_stack", "status": "missing" },
    { "skill": "Go", "category": "tech_stack", "status": "partial" }
  ]
}
```

响应体：
```json
{
  "ok": true,
  "data": {
    "suggestions": [
      {
        "skill": "Kubernetes",
        "category": "tech_stack",
        "status": "missing",
        "learning_path": {
          "concept": "理解容器编排原理、Pod/Service/Deployment 核心概念",
          "practice": "用 minikube 部署一个多服务应用，练习滚动更新和回滚",
          "validation": "完成 CKA 模拟题，能独立排查 Pod 故障"
        },
        "resources": [
          {
            "type": "document",
            "title": "Kubernetes 官方文档",
            "url": "https://kubernetes.io/docs/",
            "description": "官方概念详解和教程"
          },
          {
            "type": "course",
            "title": "Kubernetes 入门到实战",
            "url": "https://www.coursera.org/",
            "description": "Coursera 系统课程"
          },
          {
            "type": "project",
            "title": "k8s-webhook-example",
            "url": "https://github.com/",
            "description": "开源学习项目"
          },
          {
            "type": "interview",
            "title": "K8s 面试题汇总",
            "url": "https://github.com/",
            "description": "常见面试题集"
          }
        ]
      }
    ]
  }
}
```

### LLM Prompt 设计

- System prompt：你是技术学习路径规划专家，根据技能缺口生成结构化学习建议
- 输入：技能名 + 当前状态（missing/partial）
- 输出：JSON，每项含 learning_path（concept/practice/validation）和 resources（type/title/url/description）
- 约束：资源链接为推荐性质，不承诺永久有效；每项技能推荐 ≤ 4 个资源

### 前端：TutorView 组件

- 位置：右栏 Gap 报告下方，新增"AI 导师建议"区域
- 触发：Gap 报告存在且有 missing/partial 项时，显示"获取学习建议"按钮
- 渲染：
  - 每项技能一个卡片
  - 学习路径三步展示（概念→实践→验证）
  - 资源列表：类型图标 + 标题（可点击跳转）+ 描述
  - 状态选择器：已掌握 / 学习中 / 待开始
- 状态持久化：localStorage（key: `tutor-status-{skill}`），无需后端存储

## 端点

| 端点 | 方法 | 用途 |
|------|------|------|
| `/api/tutor/suggest` | POST | 基于 Gap 报告技能缺口生成学习建议 |

## 约束

- 仅处理 Gap 报告中 status 为 "missing" 或 "partial" 的技能项
- LLM 未配置时返回模板化建议（不调用 LLM）
- 资源链接由 LLM 生成，可能失效，前端提示"链接仅供参考"
- 学习状态存储在 localStorage，不持久化到后端
- 单次建议技能数 ≤ 10，避免请求过大

## 风险

- LLM 生成的资源链接可能失效 → 前端提示"链接仅供参考"
- LLM 返回内容可能无法解析为 JSON → 兜底返回模板化建议
- 技能数量过多导致 prompt 过长 → 限制 ≤ 10 项
