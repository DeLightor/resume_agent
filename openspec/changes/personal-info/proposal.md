# US-12: 个人信息管理

## 概述

在左栏知识库区域新增"个人信息"表单，用户可填写和管理个人基础信息（联系方式、求职意向、教育背景、自我评价）。数据存入版本树节点的 `content_json.personal_info`，子节点创建时自动继承父节点的 `personal_info`。

## 动机

当前 AI 生成简历时完全没有个人信息字段，导出 PDF 时姓名硬编码为"我的简历"，电话/邮箱/教育背景全部丢失。用户需要一个集中管理个人信息的入口，作为简历生成的基础数据源。

## 提议变更

### 后端

**1. PersonalInfo 数据模型**（`api/personal_info.py`）

```python
class ContactInfo(BaseModel):
    name: str = ""
    gender: str = ""
    birth_date: str = ""
    phone: str = ""
    email: str = ""
    location: str = ""
    website: str = ""
    github: str = ""
    linkedin: str = ""

class JobIntention(BaseModel):
    target_role: str = ""
    expected_salary: str = ""
    availability: str = ""

class EducationItem(BaseModel):
    school: str = ""
    degree: str = ""
    major: str = ""
    period: str = ""

class PersonalInfo(BaseModel):
    contact: ContactInfo = ContactInfo()
    job_intention: JobIntention = JobIntention()
    education: list[EducationItem] = []
    summary: str = ""
```

**2. API 端点**

| 端点 | 方法 | 用途 |
|------|------|------|
| `/api/tree/node/{node_id}/personal-info` | GET | 获取节点个人信息 |
| `/api/tree/node/{node_id}/personal-info` | PUT | 更新节点个人信息 |

**3. 节点继承机制**

在 `api/tree.py` 的 `create_node` 中，创建子节点时自动从父节点复制 `personal_info`：
- 读取父节点 `content_json.personal_info`
- 写入新节点 `content_json.personal_info`
- 不做深拷贝以外的处理，子节点独立可修改

**4. 知识库提取路径**

在 `api/personal_info.py` 中新增：
- `POST /api/personal-info/extract` — 从知识库上传的简历文件中提取个人信息
- 复用现有 `extractor.py` 的 `StructuredResume` 解析逻辑
- 将 `basic` + `education` 字段映射为 `PersonalInfo` 格式

### 前端

**1. PersonalInfoForm 组件**（`components/personal/PersonalInfoForm.tsx`）

- 位置：左栏知识库区域，在导航列表下方
- 分 4 个折叠区域：联系方式 / 求职意向 / 教育背景 / 自我评价
- 表单字段实时保存（防抖 500ms），写入当前选中节点
- 教育背景支持多条添加/删除

**2. 数据流**

- 左栏 PersonalInfoForm → `updatePersonalInfo(nodeId, data)` → PUT API
- 节点切换时重新加载 personal_info
- 生成简历时从节点 `content_json.personal_info` 读取

## 数据存储

personal_info 存储在 `resume_versions.content_json` 的 `personal_info` 字段中：

```json
{
  "personal_info": {
    "contact": { "name": "张三", "phone": "138...", "email": "...", ... },
    "job_intention": { "target_role": "后端工程师", ... },
    "education": [ { "school": "...", "degree": "本科", "major": "CS", "period": "2018-2022" } ],
    "summary": "3 年后端开发经验..."
  },
  "experience": [...],
  "projects": [...],
  "skills": [...]
}
```

## 约束

- personal_info 与 experience/projects/skills 在同一个 content_json 中，不新增数据库表
- 子节点继承是创建时的快照拷贝，不自动传播修改
- 个人信息字段全部可选，空值不渲染
- 前端表单使用防抖保存，避免频繁 API 调用

## 风险

- 节点切换时表单数据可能丢失 → 切换前自动保存，切换后重新加载
- content_json 结构变更影响现有功能 → personal_info 作为新字段添加，不影响现有字段
- 继承的数据可能过时 → UI 标注"继承自父节点"，提示用户检查
