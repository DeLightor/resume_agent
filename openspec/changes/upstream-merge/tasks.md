# US-17: 上游变更检测与提示 - 任务清单

## 后端

- [ ] schema.sql 新增 has_upstream_update + upstream_changes 列
- [ ] init_db.py 添加幂等迁移逻辑（ALTER TABLE）
- [ ] 创建 api/upstream.py
  - [ ] _propagate_upstream_changes() 变更传播逻辑
  - [ ] _get_children() 递归获取子节点
  - [ ] _diff_personal_info() 字段级差异对比
  - [ ] GET /tree/node/{node_id}/upstream-changes
- [ ] 修改 personal_info.py update_personal_info 触发传播
- [ ] 修改 tree.py get_tree 返回 has_upstream_update
- [ ] 注册路由到 router.py
- [ ] 编写测试 test_upstream_api.py

## 前端

- [ ] 修改 types/tree.ts 新增 has_upstream_update 字段
- [ ] 版本树节点显示橙色徽标
- [ ] 侧栏显示"上游有 N 项变更可合并"提示

## 验证

- [ ] 后端测试通过
- [ ] 前端 typecheck 通过
- [ ] HJ 人工验收
