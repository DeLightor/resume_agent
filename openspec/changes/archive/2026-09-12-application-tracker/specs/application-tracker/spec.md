# Specification: 投递追踪与岗位-版本关联 (US-37)

## Purpose

让求职者保存每次投递所使用的简历版本和职位上下文，并在同一处管理后续跟进。

## ADDED Requirements

### Requirement: 创建记录时冻结投递版本

系统 SHALL 在创建投递记录时从服务端读取指定的活动简历节点，并保存该节点的版本号和完整内容快照。

#### Scenario: 节点之后被编辑

- **WHEN** 用户创建投递记录后继续编辑该简历节点
- **THEN** 投递记录仍展示创建时的版本号和内容快照
- **AND** 节点的新内容不覆盖该记录

#### Scenario: 创建目标无效

- **WHEN** 用户使用不存在或已在回收站的节点创建投递记录
- **THEN** 系统拒绝创建并返回明确错误

#### Scenario: 来源节点没有内容

- **WHEN** 用户从 `content_json` 为空的活动节点创建投递记录
- **THEN** 系统冻结空对象快照
- **AND** 后续为该节点补写内容不会修改投递快照

### Requirement: 投递状态和时间线

系统 SHALL 支持 draft、applied、hr_screen、interview、offer、rejected 和 withdrawn 状态，并为创建和每次状态变更追加不可变事件。

#### Scenario: 状态变更

- **WHEN** 用户将记录从 applied 更新为 interview 并填写说明
- **THEN** 记录显示 interview 状态
- **AND** 时间线追加包含前后状态和说明的事件

#### Scenario: 同次编辑状态与字段

- **WHEN** 用户在一次保存中同时变更状态和跟进日期
- **THEN** 时间线先追加状态变更事件、再追加字段更新事件
- **AND** 重复提交没有内容差异的保存不会新增事件

### Requirement: 投递记录防止陈旧写覆盖

系统 SHALL 为每条投递记录维护版本号，并要求更新、删除和恢复携带该版本号。

#### Scenario: 两个页面同时编辑

- **WHEN** 一个页面已保存更新，另一页面使用旧版本保存
- **THEN** 系统以 `VERSION_CONFLICT` 拒绝旧写入
- **AND** 已保存的记录和事件时间线保持不变

### Requirement: 跟进可见性

系统 SHALL 保存下一步动作和跟进日期，并在记录列表中标记未结束状态下已逾期的跟进。

#### Scenario: 逾期跟进

- **WHEN** 跟进日期早于当前时间且记录状态不是 offer、rejected 或 withdrawn
- **THEN** 列表将该记录标记为逾期

### Requirement: 可恢复的投递记录删除

系统 SHALL 软删除投递记录并允许在 30 天内恢复，且默认列表不显示已删除记录。

#### Scenario: 恢复记录

- **WHEN** 用户在删除后 30 天内恢复一条投递记录
- **THEN** 记录恢复原状态、快照和完整事件时间线
- **AND** 时间线追加恢复事件

#### Scenario: 已删除筛选

- **WHEN** 用户选择“已删除”筛选
- **THEN** 列表只显示软删除记录
- **AND** 每个记录可恢复或查看历史快照

### Requirement: 本地边界

系统 SHALL 只保存用户显式提交的投递信息，不自动投递、不访问招聘网站，也不接入邮箱或日历。

#### Scenario: 创建记录

- **WHEN** 用户创建或编辑投递记录
- **THEN** 系统不会发起任何外部网络请求或替用户提交职位申请
