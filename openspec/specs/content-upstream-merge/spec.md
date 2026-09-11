# content-upstream-merge Specification

## Purpose
TBD - created by archiving change content-upstream-merge. Update Purpose after archive.
## Requirements
### Requirement: 内容级上游决策
系统 SHALL 对工作经历、项目和技能提供基于共同基准的条目级上游差异，并允许用户接受或拒绝。

#### Scenario: 双向修改
- **WHEN** 父子对同一字段相对基准产生不同修改
- **THEN** 系统显示冲突并等待用户选择，不能静默覆盖子内容

#### Scenario: 拒绝后再次更新
- **WHEN** 用户拒绝一个上游值，之后父节点再次修改该值
- **THEN** 相同旧值不会重复提示，新值产生新的待处理差异

### Requirement: 原子决策和实时状态
系统 SHALL 校验决策关联版本并原子保存内容和合并元数据，通过 SSE 通知客户端重新读取状态。

#### Scenario: 过期确认
- **WHEN** 用户确认前父节点或子节点已经更新
- **THEN** 系统拒绝过期决策且保留当前内容

#### Scenario: 重新连接
- **WHEN** SSE 连接恢复
- **THEN** 客户端重新读取权威状态且保留未保存草稿
