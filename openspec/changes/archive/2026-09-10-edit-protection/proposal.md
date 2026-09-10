# US-32 编辑保护

## Why
PRD-v2.0 US-32：输入只在 blur 后传出、跨段落防抖会相互覆盖、写入无版本检查、生成直接覆盖、删除不可恢复。

## What Changes
统一节点版本化写入、800ms 自动保存与本地待保存草稿、AI 草稿逐字段确认、20 条历史及撤销重做、30 天子树回收站。
沿用 React/FastAPI/SQLite，无新依赖。新增写入版本契约，所有应用内客户端同步修改。

## 回滚
增量 version/deleted_at/delete_batch/history_cursor 列和 node_history 表；启动迁移幂等。
回滚代码前先导出数据：旧代码无法识别软删除，不允许直接回滚后暴露删除节点；保留数据文件和新列，不自动 DROP 或清理文件。
