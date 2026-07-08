# US-12: 个人信息管理 - 任务清单

## 后端

- [ ] 创建 `backend/src/resume_agent/api/personal_info.py`
  - [ ] 定义 `ContactInfo` / `JobIntention` / `EducationItem` / `PersonalInfo` Pydantic 模型
  - [ ] `GET /tree/node/{node_id}/personal-info` 端点
  - [ ] `PUT /tree/node/{node_id}/personal-info` 端点
  - [ ] `POST /personal-info/extract` 从知识库提取个人信息
- [ ] 修改 `api/tree.py` 的 `create_node`
  - [ ] 创建子节点时从父节点继承 `personal_info`
- [ ] 注册路由到 `api/router.py`
- [ ] 编写测试 `backend/tests/test_personal_info_api.py`
  - [ ] test_get_personal_info
  - [ ] test_update_personal_info
  - [ ] test_get_nonexistent_node
  - [ ] test_inherit_personal_info_on_create
  - [ ] test_personal_info_default_empty
  - [ ] test_extract_from_knowledge_base

## 前端

- [ ] 创建 `frontend/src/types/personal.ts`
  - [ ] PersonalInfo / ContactInfo / JobIntention / EducationItem 类型
- [ ] 创建 `frontend/src/components/personal/PersonalInfoForm.tsx`
  - [ ] 4 个折叠区域：联系方式 / 求职意向 / 教育背景 / 自我评价
  - [ ] 联系方式：姓名、性别、出生年月、电话、邮箱、所在城市、个人网站、GitHub、LinkedIn
  - [ ] 求职意向：目标岗位、期望薪资、到岗时间
  - [ ] 教育背景：多条添加/删除（学校、学历、专业、时间段）
  - [ ] 自我评价：多行文本
  - [ ] 防抖保存（500ms）
  - [ ] 节点切换时重新加载
  - [ ] 继承标注提示
- [ ] 添加 `getPersonalInfo` / `updatePersonalInfo` 到 `api.ts`
- [ ] 集成到 `LeftPanel.tsx`（导航列表下方）

## 验证

- [ ] 后端测试全部通过
- [ ] 前端 typecheck + build 通过
- [ ] HJ 人工验收
