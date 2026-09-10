# US-32 Design

## 范围与工程评审
高风险：节点所有写入与删除边界。HJ 2026-09-09 已批准方案并要求开始。只做 US-32，不夹带 US-31 已归档问题。

## 存储与契约
- resume_versions 新增 version INTEGER DEFAULT 0、deleted_at、delete_batch、history_cursor；content_json.version 同步返回。
- node_history 保存 node_id、序号、摘要、时间、完整内容快照。初次写入前保存基线，保留最近20条；相同内容不新增记录；撤销后新写丢弃 redo 分支。
- services/node_content.py 统一读取/原子版本检查/写入/历史；expected_version 不匹配返回 HTTP409，删除或过期节点不可读写。
- tree 单节点/列表返回 version。PUT /tree/node/{id} 接受 {content_json,expected_version,title?}；缺少写版本返回 HTTP428。
- GET /tree/node/{id}/history -> {version,can_undo,can_redo,entries:[{id,summary,created_at}]}；POST /tree/node/{id}/undo、redo body {expected_version} 返回新版节点。
- DELETE /tree/node/{id} 将当前子树一批软删除（master 禁止）。GET /tree/trash -> {items:[{node_id,title,deleted_at,expires_at,delete_batch}]}。POST /tree/node/{id}/restore 恢复同批子树；活跃祖先缺失返回409。30天后不可恢复；本次不自动物理清理，避免不可逆误删。
- 已软删节点不能经 Agent、生成、导入去重、导出/合并等其他入口复活或改写。

## 跨入口
现有 personal-info / section / section-order / upstream 写请求通过 If-Match 传客户端版本；内部保存同时验证读取时版本。前端使用统一全内容 PUT 保存编辑草稿，其他入口更新版本契约。
生成 full/regenerate 仅返回 {content,base_version,...原响应}，不写树；前端 diff 采纳后 PUT expected_version=base_version。Agent 保留已有确认门禁，write_node 强制包含读取到的 content.version，避免覆盖门禁期间的新编辑。
导入已有方向时读取版本后经共享服务写入，形成历史；新建节点保持现有接口。

## 前端
以节点 ID 为键的草稿与单条串行保存队列，onChange 即向草稿传值，800ms debounce；切换前 flush，卸载/刷新保留 localStorage 草稿（仅本机，不把 API key 放入）。保存失败保留草稿，显示冲突/重试；冲突不自动覆盖，用户选择重新加载最新内容。
个人信息与预览共用保存契约；跨面板版本冲突也明确展示。
AI diff 复用现有旧值/新值与逐项接受拒绝范式，按对象叶子路径、数组条目递归差异，全部选择后提交一次；提交时再次检查版本。
历史按钮与快捷键 Cmd/Ctrl+Z、Shift+Z，只在非输入控件上下文操作节点历史；先 flush 再撤销，避免丢当前草稿。

## 失败矩阵与验证
- 并发相同版本：仅一个写入成功；版本和快照同事务。
- 无变化：无历史膨胀；20条上限、撤销重做边界、撤销后新编辑断开redo。
- 软删与子树恢复：保留内容，原本已删子节点不被误恢复；过期/父节点删除拒绝恢复；跨API不可访问。
- 生成期间手动编辑：草稿采纳返回409且保留手工内容。
- 防抖：多字段不互相覆盖、中文输入法组合、切节点/刷新不丢草稿、保存出错不显示成功。
后端 pytest + ruff，前端 tsc/build + 本机浏览器交互。无新增框架依赖。


## Implementation/review refinements (2026-09-09)

- Generation also returns `base_content`, an immutable copy of the exact read snapshot, so partial approvals cannot overwrite fields using an older client-side base.
- Personal-info, ordering and preview share the same per-node queue. History and upstream actions use the queue's known version after flush; they never silently acquire a newer version as permission to mutate unseen content.
- Restore after a lost save acknowledgement recognizes identical server/draft content (excluding only top-level version); differing drafts remain conflicts.
- Full-content personal-info writes and personal-info undo/redo recompute upstream notifications. Node creation locks before parent validation, preventing a live child under a concurrently deleted parent.
- AI review uses a generation mutex, resets choices for each draft, and compacts accepted appended array items without holes.
- Verification and manual acceptance handoff are recorded in verification.md. HJ acceptance remains pending; no archive, commit, merge or push has occurred.
