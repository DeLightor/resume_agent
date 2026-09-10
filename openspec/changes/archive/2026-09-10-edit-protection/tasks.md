# US-32 Implementation Plan

Goal: 编辑不丢字、AI不覆盖、误删可恢复。Spec: design.md；技术栈沿用现有项目。

- [x] 阅读PRD及全部节点写入入口；HJ确认方案；建立隔离分支
- [x] 工程评审：确认事务边界、版本冲突、草稿时序、历史游标与软删子树恢复
- [x] 存储TDD：tests/test_edit_protection.py 红→node_content/schema/init_db实现→绿
- [x] tree API：版本化保存、历史/undo/redo、trash/restore，拒绝已删除节点
- [x] 其他后端入口：个人信息/段落/排序/上游/Agent/导入统一写入与版本检查
- [x] AI full/regenerate 不写节点，返回base_version与草稿；生成时并发编辑测试
- [x] 前端：串行800ms自动保存、草稿恢复、保存状态/冲突、切节点flush
- [x] 前端：AI叶子diff选择、历史及键盘撤销、回收站恢复
- [x] 全量pytest、ruff、tsc/build、OpenSpec严格校验、diff卫生
- [x] 独立交付review及修复
- [x] 浏览器QA与测试服务启动
- [x] HJ人工验收：2026-09-10 确认通过并授权归档提交
