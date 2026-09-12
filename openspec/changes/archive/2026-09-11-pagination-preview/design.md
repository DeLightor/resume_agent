# US-34 设计方案：预览分页与一致性校验

状态：方案起草中，等待 HJ 评审确认。

## 1. 分页几何计算模型
- **A4 物理宽高比**：标准 A4 尺寸为 210mm × 297mm，高宽比恒定为 $\sqrt{2} \approx 1.4142$。
- **页面高度动态映射**：
  - 容器实际渲染宽度为 $W_{container}$（96 DPI 下 A4 标准宽度为 ~794px，或 Tailwind 容器宽度如 672px/768px）。
  - 单页标准高度基准：$H_{page} = \text{Math.round}(W_{container} \times 1.4142)$。
  - 页面总高度：通过 `containerRef.current.scrollHeight` 获取真实内容高度 $H_{content}$。
  - 计算总页数：$N_{pages} = \max(1, \lceil H_{content} / H_{page} \rceil)$。
- **监听与重算触发**：
  - 采用 `ResizeObserver` 监听预览容器的宽高变化。
  - 在内容编辑、段落展开/收起、字体加载完成后自动触发分页线重算。

## 2. 分页指示与视觉层设计
- **非侵入式分页标尺（Page Dividers）**：
  - 在 $Y = H_{page} \times k$ ($k = 1, 2, \dots, N_{pages}-1$) 的位置渲染绝对定位的分页虚线。
  - 设置 `pointer-events-none`，绝对不干扰内联编辑（`EditableText`、`EditableSummary`）及重新生成按钮点击。
  - 虚线中央显示优雅的药丸标签：`✂️ A4 分页线 · 第 k 页结束`。
- **页码与目标页数控制条（Pagination Toolbar）**：
  - 在 `ResumePreview` 顶部常驻轻量指示条：
    - 当前页数徽章（如 `1 页 / 目标 1 页`）。
    - 目标页数切换选择（默认为 1 页，可切换为 2 页）。
  - **超页预警状态（Overflow Banner）**：
    - 当 $N_{pages} > N_{target}$ 时，指示条变为橙色/琥珀色预警。
    - 提示文字：`⚠️ 内容已超出目标页数（当前 2 页）。技术简历建议保持单页，请精简亮点或调整段落。`

## 3. 前后端排版一致性保障
- 后端 ReportLab PDF 生成器（[pdf_builder.py](backend/src/resume_agent/export/pdf_builder.py)）使用 A4 绝对坐标（595.27 pt × 841.89 pt）。
- 校验抽检机制：
  - 编写自动化抽检测试 `tests/test_export_pagination.py`。
  - 测试标准单页数据在 PDF 构建器中生成的总页数是否为 1；超长数据生成的总页数是否为 2。
  - 验证前端基于比例的高度推断与后端渲染的页数严格保持同向一致性。

## 4. 容错与兼容性
- 兼容全部 6 款内置模板（`modern`, `classic`, `tech`, `minimal`, `two_column`, `academic`）。
- 保证无内容时的空白占位提示不受影响。
