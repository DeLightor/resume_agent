# US-37 实施计划：投递追踪与岗位-版本关联

## 1. 规格与评审

- [x] 建立隔离工作树 `codex/application-tracker`，核对版本树、JD 和导航现状
- [x] 写入投递记录、不可变快照、状态和软删除语义
- [x] 工程评审：确认 SQLite 事务、节点软删除兼容、API 契约和测试矩阵
- [x] 设计评审：确认看板、详情抽屉和节点创建入口的交互

## 2. 存储与 API（TDD）

- [x] 先写 `backend/tests/test_application_tracker.py`：建表和已有数据库迁移、来源节点/空快照、并发版本冲突、事件顺序、非法状态/筛选/日期、逾期和软删除恢复边界
- [x] 运行新测试，确认在实现前失败
- [x] 在 `schema.sql` 与 `init_db.py` 添加两张表、CHECK/索引和幂等迁移登记
- [x] 新建 `services/application_tracker.py`，实现 RFC 3339 UTC 验证、注入时钟、事务、快照、事件、乐观锁、列表、详情、更新、软删除和恢复
- [x] 新建 `api/applications.py`，定义请求模型并注册路由
- [x] 运行应用追踪测试及现有树/数据库回归测试，确认通过

## 3. 前端（TDD）

- [x] 先写纯函数测试：状态标签、逾期判定、编辑后 JD 负载和创建负载不得含客户端简历快照
- [x] 运行前端测试，确认在实现前失败
- [x] 新增 `types/application.ts` 与 `api.ts` 调用，和后端契约一致
- [x] 提升 JD 卡片编辑状态；新建投递看板、详情抽屉与创建/编辑表单；表单失败保留输入并处理版本冲突
- [x] 在 `Workspace`、`GlobalToolbar`、`MainLayout` 和 `CenterPanel` 接入导航与选中节点创建入口；岗位只预填可信 JD 值，其他情况要求填写
- [x] 运行前端类型检查、纯函数测试和生产构建

## 4. 验证与交付

- [x] 执行完整 pytest、Ruff、TypeScript、生产构建、OpenSpec 严格校验和 `git diff --check`
- [x] 交付前代码审查；修复所有 must-fix 项并复验
- [x] 真实浏览器 QA：创建、快照隔离、状态流转、逾期筛选、软删除/恢复、刷新恢复
- [x] 启动本地服务，提供 HJ 人工验收步骤；未经 HJ 通过不归档、不合并到 `develop`
- [x] 经 HJ 明确授权后归档、提交、合并到 `develop` 并推送；不合并 `main`，除非 HJ 另行指示
