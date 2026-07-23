# US-7: PDF 导出

## 概述

将 AI 生成结果（experience / projects / skills）渲染为 ATS 友好的 PDF 文件，支持一键下载。

## 技术方案

- 后端：reportlab（纯 Python，文本可选，ATS 友好）
- 模板：modern（简洁现代风，Helvetica 字体）
- 前端：fetch blob → 浏览器下载

## 端点

`POST /api/export/pdf`
- 请求体：`{ resume_data, job_title, company }`
- 响应：`application/pdf` 文件

## 约束

- PDF 文本可选可复制（ATS 可解析）
- 不引入系统级依赖（weasyprint 需要 cairo）
- 导出延迟 ≤ 3s
