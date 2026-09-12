# US-36 设计方案：应届生追问式冷启动 (素材挖掘)

## 1. 数据模型设计 (SQLite)

在 SQLite 中增加 `material_mining_sessions` 数据表：
```sql
CREATE TABLE IF NOT EXISTS material_mining_sessions (
    id TEXT PRIMARY KEY,
    category TEXT NOT NULL CHECK (category IN ('course_project', 'competition', 'research', 'club', 'internship')),
    title TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('in_progress', 'completed', 'abandoned')),
    current_step INTEGER NOT NULL DEFAULT 1,  -- 1(S) -> 2(T) -> 3(A) -> 4(R) -> 5(completed)
    context_json TEXT NOT NULL DEFAULT '{}',  -- 存储各阶段已问答草稿 {"step_1": ..., "step_2": ..., "answers": [...]}
    star_result_json TEXT,                    -- 最终提炼出的结构化 STAR 对象与 bullet points
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_mining_sessions_status ON material_mining_sessions(status, updated_at DESC);
```

### 字段说明：
- `id`: UUID 唯一标识。
- `category`:
  - `course_project`: 课程设计 / 期末大作业 / 实验项目
  - `competition`: 技术竞赛（如 ACM/ICPC、Kaggle、数学建模、创客大赛）
  - `research`: 实验室科研 / 学术课题 / 毕业论文
  - `club`: 学生社团 / 志愿组织 / 活动主办
  - `internship`: 早期实操 / 实习兼职经历
- `title`: 经历/项目名称（如「手写 Mini-Redis 数据库」）。
- `status`: `in_progress`（进行中/草稿）、`completed`（已提炼或已入库）、`abandoned`（已放弃）。
- `current_step`: 当前步骤序号（1: S 背景, 2: T 难点, 3: A 动作, 4: R 结果, 5: 完成）。
- `context_json`: 阶段性回答历史，支持断点续挖。
- `star_result_json`: 提炼出的标准化 STAR 结构与建议 bullet points 列表。

---

## 2. 五大专业追问模板与 STAR 状态机

### 2.1 类别元数据与初始引导
系统预置五大类别的提问策略与示例提示：

| 分类 | 默认标题占位 | 核心追问重点 | 典型量化指标引导 |
|------|-------------|-------------|-----------------|
| `course_project` | 如「基于 Raft 的分布式 KV 存储」 | 独立设计模块、协议实现、并发与容错处理 | QPS/吞吐量、测试覆盖率、并发连接数、课程评分 |
| `competition` | 如「全国大学生数学建模竞赛一等奖项目」 | 赛题难点、算法选型、个人核心代码贡献 | 准确率/MAP、排名（如 Top 2%）、数据量级 |
| `research` | 如「多模态大模型幻觉抑制算法研究」 | 实验 Baseline 对比、创新机制、消融实验 | 评价指标相对提升%、收敛速度加速倍数、论文产出 |
| `club` | 如「开源技术俱乐部年度 Hackathon 主办」 | 组织规模、活动统筹、突发状况解决 | 参与人数、宣传曝光量、满意度%、赞助金额 |
| `internship` | 如「基础架构组研发实习」 | 真实业务场景、协同交付、性能瓶颈调优 | 接口耗时降低 ms、集群资源节省%、发布零故障 |

### 2.2 STAR 四步递进式状态流转
- **Step 1: Situation（背景与目标）**
  - 师兄提问：“先简单跟我聊聊，这个项目/经历是在什么背景下启动的？当时设定的目标是什么，你们团队有多少人，你的分工角色是什么？”
- **Step 2: Task（核心挑战与难点）**
  - 师兄提问：“在你的模块里，遇到最棘手的挑战或难点是什么？比如：有没有遇到性能瓶颈、数据不一致、或者算法效果上不去的卡点？”
- **Step 3: Action（具体动作与方案）**
  - 师兄提问：“针对刚才说的难点，你具体采取了哪些技术方案和动作？比如用了什么核心技术栈/组件，如何设计或排查解决的？”
- **Step 4: Result（结果产出与量化指标）**
  - 师兄提问：“太棒了！最后这个项目的成果和落地效果怎么样？有没有具体的测试数据、对比指标、或者老师/评委的评价？”

---

## 3. 智能提炼与向量语义查重

### 3.1 STAR 提炼提示词
由 LLM 分析完整的四步问答上下文，提炼生成如下 JSON 结构：
```json
{
  "summary": "一句简短概括的技术项目定位",
  "situation": "背景与目标",
  "task": "个人核心职责与关键挑战",
  "action": "具体使用的技术方案与攻坚手段",
  "result": "量化收益与最终成果",
  "tech_stack": ["Go", "Raft", "gRPC", "RocksDB"],
  "bullet_points": [
    "负责分布式一致性协议核心模块设计，基于 Go 语言实现 Raft 选举与日志复制机制...",
    "针对网络分区与节点宕机场景，设计心跳超时自适应调整与快照压缩方案，降低网络开销 35%...",
    "通过压测工具模拟高并发写入，实现单集群 12,000+ QPS 吞吐，最终以专业排名前 5% 获优秀课程设计评价。"
  ]
}
```

### 3.2 向量语义查重机制 (`Chroma Deduplication`)
在提炼出素材后，先提取其核心描述（`summary` 与合并后的 `bullet_points` 文本），调用 Chroma 知识库集合执行相似度查询：
- 查询 `n_results = 3`。
- 计算余弦相似度分数 `score = 1.0 - distance`。
- 若最高相似度 `score >= 0.85`，判定为**疑似重复素材**，在返回结果中标记 `is_duplicate: True`，并附带最相似已有素材的摘要，由用户确认“覆盖更新”或“依然保留新增”。
- 若 `score < 0.85`，判定为**全新素材**。

---

## 4. 知识库自动化落库闭环 (`commit`)

当用户在前端预览微调后点击【确认加入知识库】：
1. 后端将 STAR 成果格式化为标准的 Markdown 文档：
   ```markdown
   # [素材挖掘] 课程设计 - 分布式 KV 存储

   > 分类：课程设计 | 来源：对话挖掘 | 时间：2026-09-11

   ## 项目定位
   ...
   ## 技术栈
   Go, Raft, gRPC, RocksDB

   ## 核心经历 (STAR Bullet Points)
   - 负责分布式一致性协议核心模块设计...
   - 针对网络分区与节点宕机场景...
   - 通过压测工具模拟高并发写入...

   ## 详细背景与动作记录
   ...
   ```
2. 保存至本地物理文件 `files_root/knowledge/[素材挖掘] {title}_{uuid}.md`。
3. 在 SQLite `upload_records` 中插入一条记录，`source_type` 标记为 `chat_mining`。
4. 调用知识库切片分块（`chunk_text`）与向量化索引（`_index_upload`），写入 SQLite `knowledge_chunks` 与 Chroma 向量集合。
5. 将当前挖掘会话标记为 `completed`。
6. 前端收到成功响应，知识库资产列表与切片统计实时刷新。

---

## 5. 后端 API 路由设计 (`/api/mining`)

| 方法 | 路径 | 功能说明 |
|------|------|----------|
| `GET` | `/api/mining/templates` | 获取 5 个分类的基础模板元数据与提示参考 |
| `POST` | `/api/mining/sessions` | 创建新挖掘会话（传入 `category`, `title`） |
| `GET` | `/api/mining/sessions` | 获取历史挖掘会话列表（支持筛选活跃/进行中草稿） |
| `GET` | `/api/mining/sessions/{id}` | 获取单个挖掘会话详情（包含当前步数与问答历史） |
| `POST` | `/api/mining/sessions/{id}/answer` | 提交某一阶段回答，并由师兄 Agent 返回反馈与下一步提问 |
| `POST` | `/api/mining/sessions/{id}/synthesize` | 生成 STAR 结构化草稿，并触发 Chroma 查重检测 |
| `POST` | `/api/mining/sessions/{id}/commit` | 用户确认入库，生成物理 md、写入 upload_records 与向量索引 |
| `DELETE` | `/api/mining/sessions/{id}` | 放弃或删除指定挖掘草稿 |

---

## 6. 前端组件与交互设计

1. **入口呈现**：
   - 在 `KnowledgeManagement.tsx`（知识库管理页）顶部添加轻量渐变引导横幅：
     - *“零经历不知道写什么？让师兄像面试官一样帮你深挖大作业、比赛与社团经历”*，附带【💡 开启素材挖掘】醒目按钮。
2. **向导抽屉 (`MaterialMiningDrawer.tsx`)**：
   - **步骤进度指示器**：1. 背景目标(S) -> 2. 核心难点(T) -> 3. 具体动作(A) -> 4. 产出量化(R) -> 5. 提炼入库。
   - **师兄气泡与提示示例**：气泡展示师兄提问与鼓励话语，下方提供“点击参考模版答案”供灵感参考。
   - **自动存盘与断点续答**：关闭抽屉时提示“已自动为您保存当前进度”，随时可再次展开继续。
3. **STAR 成果卡片与查重确认**：
   - 包含 STAR 结构化展示与高光 Bullet Points（支持一键快速微调文字）。
   - 若检测到相似度 ≥ 85%，呈现橙色“已存在类似经历”提示；
   - 点击【一键沉淀入知识库】，伴随绿色成功状态与切片徽标变动。
