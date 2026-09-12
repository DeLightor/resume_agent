"""应届生追问式冷启动素材挖掘服务（US-36 graduate-material-mining）。

覆盖：
1. 五大分类模板元数据（课设、竞赛、科研、社团、实习）。
2. 会话管理（CRUD、断点续挖与进度持久化）。
3. 师兄式 STAR 递进问答交互。
4. STAR 结构化成果与简历 Bullet Points 提炼。
5. Chroma 向量相似度语义查重。
6. 一键 Markdown 生成与知识库向量化入库。
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from resume_agent.db.connection import get_connection

logger = logging.getLogger("resume_agent")

MINING_CATEGORIES: tuple[str, ...] = (
    "course_project",
    "competition",
    "research",
    "club",
    "internship",
)

MINING_TEMPLATES: list[dict[str, Any]] = [
    {
        "category": "course_project",
        "title": "课程设计 / 期末大作业",
        "icon": "💻",
        "description": "深挖课设独立设计模块、协议与底层机制实现、并发与稳定性优化",
        "steps": [
            {
                "step": 1,
                "title": "背景与目标 (Situation)",
                "question": "师兄先跟你聊聊：这个项目/大作业是在什么课程或背景下做的？当时设定的核心目标是什么？团队多少人，你负责哪部分？",
                "example": "例如：计算机系统设计大作业，3 人团队，我担任组长负责分布式一致性 KV 存储引擎核心设计与网络通信模块。",
            },
            {
                "step": 2,
                "title": "核心挑战与难点 (Task)",
                "question": "在你负责的模块里，遇到最棘手的挑战或技术瓶颈是什么？比如有没有遇到性能瓶颈、数据不一致、或排查很久的 Bug？",
                "example": "例如：网络瞬断导致的节点选主脑裂问题，以及高并发写入时磁盘 I/O 阻塞导致响应延迟超标。",
            },
            {
                "step": 3,
                "title": "具体方案与攻坚动作 (Action)",
                "question": "为了解决刚才这个挑战，你具体采用了哪些技术栈、组件或算法设计？排查与实现过程中做了哪些针对性工作？",
                "example": "例如：基于 Go 实装 Raft 一致性算法选主与日志复制机制，使用 gRPC 实现节点通信；并引入 LSM-Tree 存储引擎与 mmap 提升读写吞吐。",
            },
            {
                "step": 4,
                "title": "结果收益与量化指标 (Result)",
                "question": "太棒了！最后这个项目的运行效果和成果怎么样？有没有具体的测试数据、压测指标，或者老师/评委的评价？",
                "example": "例如：通过 Jepsen 混沌测试验证零数据丢失，压测写入吞吐达到 1.5 万 QPS，最终期末评选以全系第 1 名获优秀课程设计。",
            },
        ],
    },
    {
        "category": "competition",
        "title": "技术 / 学科竞赛",
        "icon": "🏆",
        "description": "突出赛题难度、核心算法模型创新、攻坚瓶颈与获奖排名指标",
        "steps": [
            {
                "step": 1,
                "title": "比赛背景与赛题 (Situation)",
                "question": "来跟我讲讲这次比赛：是什么级别的竞赛？赛题要求解决什么现实问题？团队分工里你主要负责哪一块？",
                "example": "例如：全国大学生数学建模竞赛（国家级），赛题为复杂物流网络动态车辆路径规划（VRP），我负责核心模型设计与启发式算法编程求解。",
            },
            {
                "step": 2,
                "title": "赛题难点与痛点 (Task)",
                "question": "在解题或算法建模过程中，最大的算法难点或数据挑战是什么？",
                "example": "例如：节点规模达到 500+ 时传统蚁群算法陷入局部最优，且动态订单插单导致实时重调度计算耗时超过 5 分钟。",
            },
            {
                "step": 3,
                "title": "核心算法与方案 (Action)",
                "question": "你们是如何突破这个瓶颈的？采用了什么创新的算法结构、数据预处理或代码优化方案？",
                "example": "例如：引入变邻域搜索（VNS）与自适应遗传退火混合算法，编写 C++ 扩展进行矩阵加速计算，并设计自适应网格索引加速空间临近点检索。",
            },
            {
                "step": 4,
                "title": "竞赛成果与排名 (Result)",
                "question": "最终的求解效果和竞赛成绩如何？相对 baseline 提升了多少？最终获得了什么奖项？",
                "example": "例如：求解时间由 5 分钟压缩至 18 秒，总路径成本降低 24%，在全国 3000+ 参赛队伍中位列前 1%，荣获国家一等奖。",
            },
        ],
    },
    {
        "category": "research",
        "title": "实验室科研 / 毕业论文",
        "icon": "🔬",
        "description": "提炼学术创新点、实验 Baseline 对比、消融实验、论文发表或专利",
        "steps": [
            {
                "step": 1,
                "title": "课题背景与研究目标 (Situation)",
                "question": "聊聊你的科研课题：实验室主攻哪个研究方向？这个课题主要解决学术界/工业界哪个尚未完全解决的问题？",
                "example": "例如：在智能媒体计算实验室参与多模态大模型研究课题，主攻高分辨率图文对齐中细粒度特征丢失与显存爆炸瓶颈。",
            },
            {
                "step": 2,
                "title": "技术瓶颈与现有方案缺陷 (Task)",
                "question": "现有的经典方法（Baseline）存在什么关键缺陷？你的任务核心指标是什么？",
                "example": "例如：传统全自注意力机制随序列长度二次方暴涨，在 4K 分辨率下单卡显存直接 OOM，且无法捕捉局部细微语义变化。",
            },
            {
                "step": 3,
                "title": "创新架构与实验攻坚 (Action)",
                "question": "你提出了什么创新的模块或机制？实验中是如何验证有效性的？",
                "example": "例如：提出基于语义熵的自适应动态稀疏注意力机制，编写 PyTorch 自定义 CUDA 算子加速，并在多卡集群完成 5 组对比消融实验。",
            },
            {
                "step": 4,
                "title": "实验效果与学术产出 (Result)",
                "question": "最终在公开数据集上的表现如何？相对 SOTA 提升了多少？是否有论文发表或开源？",
                "example": "例如：在 POPE/MME 基准集上幻觉错误率降低 28.5%，显存峰值降低 40%，论文被计算机视觉顶级会议 CVPR 录用（学生一作）。",
            },
        ],
    },
    {
        "category": "club",
        "title": "学生社团 / 组织活动",
        "icon": "🤝",
        "description": "展现领导力、项目统筹与协同落地能力、量化活动规模与影响力",
        "steps": [
            {
                "step": 1,
                "title": "社团与活动背景 (Situation)",
                "question": "说说你参与或主办的这个活动：你在社团担任什么角色？活动的目标和预期受众规模是怎样的？",
                "example": "例如：担任校开源技术俱乐部副部长，牵头统筹全校首届高校 48 小时 Hackathon 创客编程马拉松活动。",
            },
            {
                "step": 2,
                "title": "统筹难点与突发挑战 (Task)",
                "question": "筹备或落地过程中遇到了什么棘手困难？比如赞助短缺、技术支持故障、或跨团队协作摩擦？",
                "example": "例如：距离开幕仅 2 周时原定赞助商突然撤约导致资金缺口 2 万元，且比赛现场高并发提交打崩了简易判题服务器。",
            },
            {
                "step": 3,
                "title": "关键举措与组织协调 (Action)",
                "question": "你是怎么带领团队应对并解决这些挑战的？具体做了哪些工作？",
                "example": "例如：紧急对接 4 家校友企业完成二次赞助路演补齐预算；带领技术组连夜搭建 Docker 容器隔离的分布式评测沙盒解决性能瓶颈。",
            },
            {
                "step": 4,
                "title": "活动成效与量化反馈 (Result)",
                "question": "活动最终举办得如何？有多少人参与？大家以及指导老师的反馈怎么样？",
                "example": "例如：吸引全校 12 个学院共 300+ 选手组队参赛，产出 45 个创新软硬件项目，满意度调研达 98.6%，获评全校年度十佳精品社团活动。",
            },
        ],
    },
    {
        "category": "internship",
        "title": "早期实操 / 实习兼职",
        "icon": "💼",
        "description": "强调真实商业环境、业务需求承接、跨团队交付与系统性能收益",
        "steps": [
            {
                "step": 1,
                "title": "公司业务与岗位职责 (Situation)",
                "question": "聊聊这段实习经历：所在的业务团队主要负责什么系统？你入职后承接的核心模块是什么？",
                "example": "例如：在互联网公司基础平台部担任后端开发实习生，主要负责面向全公司业务线的文件与音视频上传转码网关。",
            },
            {
                "step": 2,
                "title": "业务痛点与技术诉求 (Task)",
                "question": "该系统在原有运行中有何痛点，或者业务方对你提的新需求挑战在哪里？",
                "example": "例如：原有文件分片上传直传 S3 缺乏限流，高峰期大量大文件重试导致带宽占满，平均上传失败率高达 8.4%。",
            },
            {
                "step": 3,
                "title": "方案设计与工程实践 (Action)",
                "question": "在导师指导下你具体是如何设计和实现的？用到了哪些设计模式或技术？",
                "example": "例如：基于 Go + Redis 实现断点续传与令牌桶流量控制，设计异步任务队列解耦文件转码逻辑，并增加跨机房容灾降级策略。",
            },
            {
                "step": 4,
                "title": "业务成效与上线指标 (Result)",
                "question": "功能上线后的业务指标收益如何？团队对你的评价怎样？",
                "example": "例如：大文件上传成功率从 91.6% 提升至 99.8%，峰值链路延迟降低 35%，实习期独立交付 2 个核心特性获评优秀实习生。",
            },
        ],
    },
]


@dataclass
class MaterialMiningSession:
    """素材挖掘会话数据类。"""

    id: str
    category: str
    title: str
    status: str
    current_step: int
    context: dict[str, Any]
    star_result: dict[str, Any] | None
    created_at: str | None = None
    updated_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category,
            "title": self.title,
            "status": self.status,
            "current_step": self.current_step,
            "context": self.context,
            "star_result": self.star_result,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def _parse_json_safely(text: str) -> dict[str, Any]:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
    return {}


def _row_to_session(row: dict[str, Any]) -> MaterialMiningSession:
    context = {}
    if row.get("context_json"):
        try:
            context = json.loads(row["context_json"])
        except Exception:  # noqa: BLE001
            context = {}

    star_result = None
    if row.get("star_result_json"):
        try:
            star_result = json.loads(row["star_result_json"])
        except Exception:  # noqa: BLE001
            star_result = None

    return MaterialMiningSession(
        id=str(row["id"]),
        category=str(row["category"]),
        title=str(row["title"]),
        status=str(row["status"]),
        current_step=int(row["current_step"]),
        context=context,
        star_result=star_result,
        created_at=str(row["created_at"]) if row.get("created_at") else None,
        updated_at=str(row["updated_at"]) if row.get("updated_at") else None,
    )


def get_mining_templates() -> list[dict[str, Any]]:
    """获取预置的五大经历分类模板元数据。"""
    return MINING_TEMPLATES


def create_mining_session(
    category: str,
    title: str,
    db_path: Path | str | None = None,
) -> MaterialMiningSession:
    """创建新的素材挖掘会话。"""
    clean_cat = (category or "").strip()
    clean_title = (title or "").strip()

    if clean_cat not in MINING_CATEGORIES:
        raise ValueError(f"非法经历分类: {category}，可选: {MINING_CATEGORIES}")
    if not clean_title:
        raise ValueError("标题不能为空")

    session_id = str(uuid.uuid4())
    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO material_mining_sessions (
                id, category, title, status, current_step, context_json, created_at, updated_at
            ) VALUES (?, ?, ?, 'in_progress', 1, '{}', datetime('now'), datetime('now'))
            """,
            [session_id, clean_cat, clean_title],
        )
        row = conn.execute(
            "SELECT * FROM material_mining_sessions WHERE id = ?", [session_id]
        ).fetchone()
        return _row_to_session(row)


def get_mining_session(
    session_id: str,
    db_path: Path | str | None = None,
) -> MaterialMiningSession | None:
    """按 ID 查询挖掘会话。"""
    try:
        with get_connection(db_path) as conn:
            row = conn.execute(
                "SELECT * FROM material_mining_sessions WHERE id = ?", [session_id]
            ).fetchone()
            if not row:
                return None
            return _row_to_session(row)
    except sqlite3.Error as exc:
        logger.warning("查询挖掘会话失败: %s", exc)
        return None


def list_mining_sessions(
    status_filter: str | None = None,
    db_path: Path | str | None = None,
) -> list[MaterialMiningSession]:
    """查询挖掘会话列表，支持状态过滤（如查询进行中草稿）。"""
    query = "SELECT * FROM material_mining_sessions WHERE 1=1"
    params: list[Any] = []
    if status_filter:
        query += " AND status = ?"
        params.append(status_filter)
    query += " ORDER BY datetime(updated_at) DESC, datetime(created_at) DESC"

    try:
        with get_connection(db_path) as conn:
            rows = conn.execute(query, params).fetchall()
            return [_row_to_session(r) for r in rows]
    except sqlite3.Error as exc:
        logger.warning("查询挖掘会话列表失败: %s", exc)
        return []


def save_mining_session(
    session: MaterialMiningSession,
    db_path: Path | str | None = None,
) -> MaterialMiningSession:
    """持久化保存挖掘会话更新（问答历史、步骤、状态与提炼结果）。"""
    with get_connection(db_path) as conn:
        conn.execute(
            """
            UPDATE material_mining_sessions
            SET title = ?, status = ?, current_step = ?, context_json = ?,
                star_result_json = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            [
                session.title,
                session.status,
                session.current_step,
                json.dumps(session.context, ensure_ascii=False),
                json.dumps(session.star_result, ensure_ascii=False) if session.star_result else None,
                session.id,
            ],
        )
    return get_mining_session(session.id, db_path) or session


def delete_mining_session(
    session_id: str,
    db_path: Path | str | None = None,
) -> bool:
    """删除指定素材挖掘会话。"""
    try:
        with get_connection(db_path) as conn:
            cur = conn.execute(
                "DELETE FROM material_mining_sessions WHERE id = ?", [session_id]
            )
            return cur.rowcount > 0
    except sqlite3.Error as exc:
        logger.warning("删除挖掘会话失败: %s", exc)
        return False


async def submit_step_answer(
    session_id: str,
    step: int,
    answer: str,
    llm: Any = None,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """提交某个阶段的问答回答，持久化断点并推进下一步。

    由 LLM 生成师兄风格的短评和递进引导（或平滑降级）。
    """
    session = get_mining_session(session_id, db_path)
    if not session:
        raise ValueError(f"会话不存在: {session_id}")

    clean_ans = (answer or "").strip()
    if not clean_ans:
        raise ValueError("回答内容不能为空")

    # 保存阶段回答
    session.context[f"step_{step}"] = clean_ans

    # 找到该类别的下一个步骤问题
    template = next(
        (t for t in MINING_TEMPLATES if t["category"] == session.category),
        MINING_TEMPLATES[0],
    )
    next_step_info = next((s for s in template["steps"] if s["step"] == step + 1), None)

    feedback_text = ""
    # 若配置了 LLM，调用大模型生成带有技术理解的师兄点评
    if llm and getattr(llm, "configured", False):
        try:
            prompt = (
                f"你是一位经验丰富、亲切专业的技术师兄兼大厂面试官。用户正在梳理自己的经历：\n"
                f"项目名称：{session.title}\n"
                f"经历分类：{session.category}\n"
                f"当前第 {step} 步回答：{clean_ans}\n"
                f"请用 1-2 句简洁、鼓励且懂行的话点评用户的回答，并顺理成章地引导下一问。"
                f"如果存在下一问（{next_step_info['question'] if next_step_info else '已完成四步问答'}），请自然衔接。"
            )
            resp = await llm.chat(
                system_prompt="你是一位资深技术面试官师兄，口吻亲切专业、鼓励为主、直击技术关键点。",
                user_content=prompt,
            )
            feedback_text = resp.strip()
        except Exception as exc:  # noqa: BLE001
            logger.warning("师兄追问反馈调用 LLM 失败，使用预置模板: %s", exc)

    if not feedback_text:
        if next_step_info:
            feedback_text = f"收到！理解得非常清楚。接下来我们聊聊第二项：{next_step_info['question']}"
        else:
            feedback_text = "太棒了！四项核心内容已全部梳理完毕，我马上为你进行专业 STAR 简历语言提炼！"

    if step < 4:
        session.current_step = step + 1
    else:
        session.current_step = 5  # 四步完成进入提炼阶段

    saved = save_mining_session(session, db_path)
    return {
        "session": saved.to_dict(),
        "feedback": feedback_text,
        "next_step": next_step_info,
    }


async def synthesize_star_result(
    session_id: str,
    llm: Any = None,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """将收集到的 4 步问答历史提炼为 STAR 结构化数据与 Bullet Points。"""
    session = get_mining_session(session_id, db_path)
    if not session:
        raise ValueError(f"会话不存在: {session_id}")

    answers = session.context
    s1 = answers.get("step_1", "")
    s2 = answers.get("step_2", "")
    s3 = answers.get("step_3", "")
    s4 = answers.get("step_4", "")

    synthesized: dict[str, Any] = {}

    if llm and getattr(llm, "configured", False):
        try:
            system_prompt = (
                "你是资深简历专家，擅长将零散、口语化的学生大作业、比赛和社团项目转化为"
                "高度专业、符合大厂招聘偏好的 STAR 简历语言。\n"
                "你必须严格返回 JSON 格式，字段要求如下：\n"
                "- summary: 一句精炼的技术项目定位（15-25 字）\n"
                "- situation: 项目背景与目标阐述\n"
                "- task: 个人承担的核心难点与职责\n"
                "- action: 具体实施的技术动作与方案设计\n"
                "- result: 成果、量化指标或客观评价\n"
                "- tech_stack: [字符串列表，涉及的关键技术栈]\n"
                "- bullet_points: [3条可以直接放进简历的 Bullet Points，每条遵循「动作动词 + 业务背景/难点 + 技术手段 + 量化产出」结构，禁止空话，突出实操]"
            )
            user_content = (
                f"经历标题：{session.title}\n"
                f"经历类型：{session.category}\n"
                f"背景与目标(S)：{s1}\n"
                f"难点与挑战(T)：{s2}\n"
                f"动作与方案(A)：{s3}\n"
                f"量化与结果(R)：{s4}\n"
            )
            raw = await llm.chat(
                system_prompt=system_prompt,
                user_content=user_content,
                response_format_json=True,
            )
            data = _parse_json_safely(raw)
            if isinstance(data, dict) and "bullet_points" in data:
                synthesized = data
        except Exception as exc:  # noqa: BLE001
            logger.warning("提炼 STAR 调用 LLM 异常，降级到规则拼接: %s", exc)

    if not synthesized:
        # 降级兜底方案
        synthesized = {
            "summary": f"针对{session.title}的核心研发与技术实践",
            "situation": s1 or "项目起步阶段负责系统整体设计与需求落地",
            "task": s2 or "攻克系统核心业务逻辑实现与关键技术瓶颈",
            "action": s3 or "通过模块化设计与技术选型落地实施方案",
            "result": s4 or "圆满达成项目预期指标并获得良好评价",
            "tech_stack": ["Git", "Python"],
            "bullet_points": [
                f"负责{session.title}核心模块设计与开发，明确技术目标并推进分工协同",
                "针对项目过程中的关键挑战，采用对应技术栈完成方案设计与工程落地",
                "项目最终顺利上线并通过各项测试指标，取得了良好的应用效果",
            ],
        }

    session.star_result = synthesized
    save_mining_session(session, db_path)
    return synthesized


def check_duplicate_in_knowledge(
    text: str,
    threshold: float = 0.85,
) -> dict[str, Any]:
    """在现有知识库中进行向量语义查重检测。

    Args:
        text: 待检测的素材文本。
        threshold: 相似度阈值（默认 0.85）。

    Returns:
        {"is_duplicate": bool, "score": float, "top_match": dict | None}
    """
    cleaned = (text or "").strip()
    if not cleaned:
        return {"is_duplicate": False, "score": 0.0, "top_match": None}

    from resume_agent.rag import chroma_client

    try:
        collection = chroma_client.get_knowledge_collection()
        if not collection or collection.count() == 0:
            return {"is_duplicate": False, "score": 0.0, "top_match": None}

        res = collection.query(query_texts=[cleaned], n_results=1)
        ids = res.get("ids", [[]])
        docs = res.get("documents", [[]])
        metas = res.get("metadatas", [[]])
        distances = res.get("distances", [[]])

        if not ids or not ids[0]:
            return {"is_duplicate": False, "score": 0.0, "top_match": None}

        dist = distances[0][0] if distances and distances[0] else 1.0
        score = round(max(0.0, 1.0 - (dist if dist is not None else 1.0)), 4)
        doc = docs[0][0] if docs and docs[0] else ""
        meta = metas[0][0] if metas and metas[0] else {}

        is_dup = score >= threshold
        top_match = {
            "text": doc[:200],
            "source_file": meta.get("source_file", "") if isinstance(meta, dict) else "",
            "score": score,
        }
        return {
            "is_duplicate": is_dup,
            "score": score,
            "top_match": top_match if is_dup else None,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("向量查重检测异常，默认不拦截: %s", exc)
        return {"is_duplicate": False, "score": 0.0, "top_match": None}


def commit_mining_to_knowledge(
    session_id: str,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """将挖掘成果格式化为物理 Markdown 文件，并自动化写入 upload_records 与向量集合。"""
    session = get_mining_session(session_id, db_path)
    if not session:
        raise ValueError(f"会话不存在: {session_id}")
    if not session.star_result:
        raise ValueError("会话尚未提炼 STAR 成果，无法入库")

    star = session.star_result
    category_title = next(
        (t["title"] for t in MINING_TEMPLATES if t["category"] == session.category),
        session.category,
    )

    # 1. 组装标准资产 Markdown
    bullets_md = "\n".join(f"- {bp}" for bp in star.get("bullet_points", []))
    tech_str = ", ".join(star.get("tech_stack", [])) or "通用技术"

    q_and_a_md = (
        f"### 详细梳理记录 (STAR 原始问答)\n\n"
        f"**背景与目标 (Situation)**:\n{session.context.get('step_1', '未填写')}\n\n"
        f"**核心挑战与难点 (Task)**:\n{session.context.get('step_2', '未填写')}\n\n"
        f"**攻坚举措与方案 (Action)**:\n{session.context.get('step_3', '未填写')}\n\n"
        f"**量化收益与评价 (Result)**:\n{session.context.get('step_4', '未填写')}\n"
    )

    md_content = f"""# [素材挖掘] {session.title}

> 分类：{category_title} | 来源：对话挖掘 | 创建时间：{session.created_at or '2026-09-11'}

## 核心定位
{star.get('summary', session.title)}

## 技术栈
{tech_str}

## 核心简历语言 (STAR 亮点条目)
{bullets_md}

## STAR 背景详述
- **情境 (Situation)**: {star.get('situation', '')}
- **任务 (Task)**: {star.get('task', '')}
- **行动 (Action)**: {star.get('action', '')}
- **结果 (Result)**: {star.get('result', '')}

---

{q_and_a_md}
"""

    # 2. 写入物理文件
    from resume_agent.config import settings

    upload_id = str(uuid.uuid4())
    knowledge_dir = settings.files_root / "knowledge"
    knowledge_dir.mkdir(parents=True, exist_ok=True)

    clean_filename = f"[素材挖掘]_{session.title}_{upload_id[:8]}.md".replace(" ", "_").replace("/", "_")
    saved_path = knowledge_dir / clean_filename
    saved_path.write_text(md_content, encoding="utf-8")

    relative_path = f"knowledge/{clean_filename}"

    # 3. 写入 upload_records
    effective_db = db_path or settings.sqlite_path
    with get_connection(effective_db) as conn:
        conn.execute(
            """
            INSERT INTO upload_records (id, file_name, file_type, file_path, parse_status)
            VALUES (?, ?, 'md', ?, 'success')
            """,
            [upload_id, clean_filename, relative_path],
        )

    # 4. 切片分块与 Chroma 向量化
    from resume_agent.rag.chunker import chunk_text
    chunks = chunk_text(md_content)
    chunk_count = len(chunks)

    from resume_agent.rag.chroma_client import get_knowledge_collection
    collection = get_knowledge_collection()

    chroma_ids: list[str] = []
    chroma_docs: list[str] = []
    chroma_metas: list[dict[str, Any]] = []

    with get_connection(effective_db) as conn:
        for idx, chk in enumerate(chunks):
            cid = str(uuid.uuid4())
            emb_id = f"{upload_id}_{idx}"
            meta = {
                "source_file": clean_filename,
                "upload_id": upload_id,
                "chunk_index": idx,
                "category": session.category,
                "direction": "chat_mining",
            }
            conn.execute(
                """
                INSERT INTO knowledge_chunks (id, source_file, chunk_text, embedding_id, metadata_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                [cid, clean_filename, chk, emb_id, json.dumps(meta, ensure_ascii=False)],
            )
            chroma_ids.append(emb_id)
            chroma_docs.append(chk)
            chroma_metas.append(meta)

    if chroma_ids and collection:
        try:
            collection.upsert(
                ids=chroma_ids,
                documents=chroma_docs,
                metadatas=chroma_metas,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("写入 Chroma 失败: %s", exc)

    # 5. 更新会话状态为 completed
    session.status = "completed"
    save_mining_session(session, effective_db)

    return {
        "ok": True,
        "upload_id": upload_id,
        "file_name": clean_filename,
        "file_path": relative_path,
        "chunk_count": chunk_count,
    }


__all__ = [
    "MINING_CATEGORIES",
    "MINING_TEMPLATES",
    "MaterialMiningSession",
    "get_mining_templates",
    "create_mining_session",
    "get_mining_session",
    "list_mining_sessions",
    "save_mining_session",
    "delete_mining_session",
    "submit_step_answer",
    "synthesize_star_result",
    "check_duplicate_in_knowledge",
    "commit_mining_to_knowledge",
]
