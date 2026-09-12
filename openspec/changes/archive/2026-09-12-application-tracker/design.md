# US-37 设计：投递追踪与岗位-版本关联

## 状态与范围

风险等级：高。该功能新增持久化用户业务数据、软删除和状态时间线；实现前必须完成 API/状态机评审，所有写路径以测试先行。

## 数据模型

新增 `application_records`：

| 字段 | 说明 |
| --- | --- |
| `id` | UUID |
| `resume_node_id` | 投递时选中的 `resume_versions.node_id`，仅作引用，不使用级联删除 |
| `resume_node_title` | 创建时冻结的节点显示名；节点后来进入回收站也可识别来源 |
| `resume_version` | 选中节点的乐观锁版本 |
| `resume_snapshot_json` | 选中节点完整 `content_json` 快照，创建后不可修改 |
| `company` / `role` | 投递目标，均为必填 |
| `job_url` | 可选职位链接 |
| `jd_snapshot_json` | 创建时传入的结构化 JD，可为空 |
| `status` | `draft`、`applied`、`hr_screen`、`interview`、`offer`、`rejected`、`withdrawn` |
| `next_action` / `follow_up_at` / `notes` | 用户维护的待办与备注 |
| `deleted_at` | 软删除时间；默认查询不返回 |
| `version` | 记录自身的乐观锁版本；每一次修改、删除和恢复递增 |
| `created_at` / `updated_at` | 记录时间 |

新增 `application_events`：递增 `id`、`application_id`、`event_type`、`from_status`、`to_status`、`note`、`changed_fields_json` 和 `created_at`。其中 `changed_fields_json` 只保存本次可变字段名称（不保存简历/JD 快照和备注原文），用于说明普通编辑改了什么。事件只追加，应用 API 没有更新或删除事件的路径。

`resume_node_id` 不设数据库外键：US-32 的节点回收站会软删除节点，而投递记录必须继续保留其历史快照。

## 状态语义

创建记录的默认状态是 `draft`。用户可从任一非删除状态切换到任一投递状态；这允许“拒绝后重新激活”“面试回退 HR”等现实流程，但每次变化都必须追加 `status_changed` 事件。一次 PUT 同时改状态和其他字段时，按 `status_changed` 再 `updated` 的顺序追加两条事件；无实际变化的 PUT 不增加事件，也不递增版本。`deleted_at` 独立于业务状态；删除后不允许更新，恢复后保留原有状态和时间线。

所有服务端时间存储和 API 返回均为 UTC RFC 3339 字符串（如 `2026-09-12T09:30:00Z`）；`follow_up_at` 是一个具体时刻，客户端提交时必须带时区。逾期由读取时计算：`follow_up_at` 严格早于当前 UTC 时刻、记录未软删除、状态不是 `offer` / `rejected` / `withdrawn` 即为逾期。服务层注入 `now()` 时钟以覆盖精确边界测试。系统不发送通知。

## API 契约

所有端点使用现有 `{ok, data, error}` envelope；请求体无效也由端点转换为 400 + `INVALID_ARGUMENT` envelope，而不是暴露 FastAPI 默认校验响应。不存在为 404 + `APPLICATION_NOT_FOUND` / `NODE_NOT_FOUND`，已删除而不能编辑为 409 + `APPLICATION_DELETED`，版本陈旧为 409 + `VERSION_CONFLICT`（返回当前 `version`），没有/不合法 `expected_version` 为 428/400 + `VERSION_REQUIRED` / `INVALID_ARGUMENT`。

- `POST /api/applications`：创建体严格为 `{resume_node_id, company, role, job_url?, jd_snapshot?, status?, next_action?, follow_up_at?, notes?}`。服务器在同一个 `BEGIN IMMEDIATE` 事务读取该活动节点的 `content_json` 和 `version`，复制权威快照、版本和标题；客户端不得提交简历快照或版本号。`content_json` 为 NULL 时冻结 `{}`，而不是读取节点后续内容。
- `GET /api/applications?status=&deleted=`：`status` 只能取业务状态；`deleted=exclude`（默认）只返回活动记录，`deleted=only` 只返回软删除记录，`deleted=include` 两者都返回。按 `updated_at DESC, id DESC` 排序，返回 `is_overdue`、节点标题和快照元数据；未知筛选值返回 `INVALID_ARGUMENT`。
- `GET /api/applications/{id}`：返回完整记录与按 `id ASC` 排序的事件时间线；已删除记录也可读取。
- `PUT /api/applications/{id}`：部分更新，体必须含 `expected_version`，其余字段只有出现时才更新；显式 `null` 清空可选字段，空公司/岗位/日期字符串非法。可更新公司、岗位、链接、JD 快照、待办、日期、备注和状态；禁止改动简历快照、来源节点和来源版本。`status_change_note?` 仅写入状态事件。
- `DELETE /api/applications/{id}`：请求体 `{expected_version}`，软删除并追加 `deleted` 事件。
- `POST /api/applications/{id}/restore`：请求体 `{expected_version}`，恢复 30 天内的删除记录并追加 `restored` 事件；过期返回 410 + `RESTORE_EXPIRED`。

创建时节点必须存在且未被软删除。之后即使节点被删除，记录详情仍从自身快照渲染，节点链接显示为“原版本已在回收站”。

## 前端体验

新增“投递追踪”主导航视图：上方显示状态筛选和逾期数，下方按状态展示紧凑列。点击卡片打开详情抽屉，展示投递版本、JD 摘要、待办、备注和时间线。

版本树编辑器工具栏增加“记录投递”入口。它在已有选中节点时打开确认表单：公司/岗位优先从当前结构化 JD 预填，若无 JD 则公司可用节点 `company` 预填、岗位留空；两项始终要求用户确认。节点标题不用于推断岗位。若当前工作台有结构化 JD，一并传入创建请求。JD 卡片的编辑状态必须提升至 `RightPanel`/`MainLayout`，使创建时冻结用户最后确认的结构化值；v1 不保存原始 JD 文本。创建成功后只新增记录，不更新节点。

表单提交失败时保留输入；状态色不作为唯一信息载体。软删除记录只在“已删除”筛选中可见，并提供恢复按钮。

## 数据安全与一致性

- 服务器端生成不可变简历快照，避免客户端伪造“投递版本”。
- 创建、更新、删除和恢复使用 SQLite `BEGIN IMMEDIATE`，记录与对应事件原子提交，并以 `WHERE id=? AND version=?` 做最终比较更新。
- 表定义含状态 CHECK、非空字段、`application_events.application_id` 外键（不允许硬删应用）以及 `(deleted_at, status, updated_at DESC)`、`(follow_up_at)`、`(application_id, id)` 索引；`init_db.TABLES` 和既有数据库初始化迁移均须覆盖两表。
- 日期以 RFC 3339 UTC 存储；前端以本地时区展示。
- API 不接受未知状态；空公司、岗位或无效日期返回 `INVALID_ARGUMENT`。
- 所有读取默认排除删除记录；恢复严格限制删除后 30 天内。

## 验证矩阵

测试创建时快照隔离、来源节点缺失/删除/空内容、删除节点后的历史可读、陈旧写冲突、更新/删除竞争、状态和普通编辑的事件顺序与幂等、非法状态/筛选/日期、逾期精确边界、软删除恢复及 30 天边界，并分别覆盖新库与已有 US-36 数据库升级。前端测试状态映射、编辑后的 JD 请求负载、节点切换不串写、列表/详情删除恢复与冲突刷新；浏览器 QA 覆盖从节点创建、看板更新、状态流转、逾期筛选、软删除恢复和页面刷新恢复。
