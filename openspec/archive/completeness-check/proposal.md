# US-15: 信息完整性检测 + 可编辑预览

## 概述

1. 简历生成后自动检测信息完整度，缺失字段高亮标注，完整性评分 0-100
2. 预览区内容可直接点击编辑修改
3. 检测结果以清单形式展示，可点击跳转

## 提议变更

### 后端

**1. 完整性检测 API** — `POST /api/completeness/check`

请求：`{ node_id }`
返回：
```json
{
  "score": 75,
  "checks": [
    {"field": "name", "status": "ok", "message": ""},
    {"field": "phone", "status": "missing", "message": "电话缺失"},
    {"field": "summary", "status": "weak", "message": "内容不足（<20字）"},
    {"field": "experience", "status": "ok", "count": 2},
    {"field": "projects", "status": "missing", "message": "无项目经历"}
  ]
}
```

检测规则：
- 个人信息：name/phone/email 缺失为红色，location/github 缺失不扣分
- summary：空=缺失，<20字=内容不足
- experience：空=缺失，<1条=内容不足
- projects：空=缺失，<1条=内容不足
- skills：空=缺失
- education：空=缺失

评分：每项 ok=满分，weak=半分，missing=0分，总分 100

**2. 段落编辑 API** — `PUT /api/tree/node/{node_id}/section`

请求：`{ section, data }`
- 更新 content_json 中对应段落
- section: summary/experience/projects/skills/education

### 前端

**1. 可编辑预览**
- 每个段落内容可点击进入编辑模式
- summary: textarea
- experience/projects: 每条可编辑（company/role/period/highlights）
- skills: 标签列表可增删
- 编辑后防抖保存 500ms

**2. 完整性检测面板**
- 预览区顶部显示评分（0-100）+ 评分条
- 缺失/不足字段以清单形式展示
- 点击清单项跳转到对应段落编辑
- 缺失字段在预览区红色/黄色高亮标注

## 约束

- 不引入新依赖
- 编辑直接修改 content_json，防抖保存
- 完整性检测在前端执行（不调后端，减少延迟）
