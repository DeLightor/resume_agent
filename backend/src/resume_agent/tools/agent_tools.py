"""Agent 工具集：把既有后端能力封装为 ToolSpec（US-27 agent-runtime）。

每个工具是对 service 层函数的薄封装（校验参数 → 调用 → 规范输出），
不包含业务逻辑。``ask_user`` 为特殊工具，由 AgentRunner 特判暂停，
其 execute 直接抛错以暴露误用。

工具清单（design.md 2.3）：
- retrieve_knowledge  知识库语义检索
- parse_jd           JD 文本结构化提取
- analyze_gap        技能 Gap 分析
- read_node/write_node  版本树节点内容读写
- list_templates     简历模板列表（render_preview 的后端等价物）
- export_pdf         PDF 导出
- web_search         Tavily Web 搜索
- ask_user           向用户提问（暂停循环等待输入）
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from resume_agent.agents.registry import ToolRegistry, ToolSpec
from resume_agent.export.pdf_builder import build_pdf
from resume_agent.export.templates import list_templates
from resume_agent.services.gap_analyzer import analyze_gap
from resume_agent.services.jd_extract import extract_jd_fields
from resume_agent.services.knowledge_search import search_knowledge
from resume_agent.services.node_content import get_node_content, save_node_content
from resume_agent.tools.tavily_search import search_web

logger = logging.getLogger("resume_agent")

ASK_USER_TOOL_NAME = "ask_user"

# agent-write-guard: write_node 由 AgentRunner 特判暂停（等待用户确认），
# 确认后仍经 registry.execute 执行本文件中的 _write_node。
WRITE_NODE_TOOL_NAME = "write_node"


async def _retrieve_knowledge(args: dict[str, Any]) -> list[dict[str, Any]]:
    """知识库语义检索。"""
    query = str(args.get("query", "")).strip()
    if not query:
        return {"error": "query 不能为空"}  # type: ignore[return-value]
    top_k = args.get("top_k", 3)
    if not isinstance(top_k, int) or top_k < 1 or top_k > 10:
        top_k = 3
    return search_knowledge([query], top_k=top_k)


async def _parse_jd(args: dict[str, Any]) -> dict[str, Any]:
    """JD 文本结构化提取。"""
    jd_text = str(args.get("jd_text", "")).strip()
    if not jd_text:
        return {"error": "jd_text 不能为空"}
    return await extract_jd_fields(jd_text)


async def _analyze_gap(args: dict[str, Any]) -> dict[str, Any]:
    """技能 Gap 分析。"""
    structured_jd = args.get("structured_jd")
    if not isinstance(structured_jd, dict) or not structured_jd:
        return {"error": "structured_jd 不能为空"}
    return await analyze_gap(structured_jd)


async def _read_node(args: dict[str, Any]) -> Any:
    """读取版本树节点内容。"""
    node_id = str(args.get("node_id", "")).strip()
    if not node_id:
        return {"error": "node_id 不能为空"}
    content = get_node_content(node_id)
    if content is None:
        return {"error": f"节点不存在: {node_id}"}
    return content


async def _write_node(args: dict[str, Any]) -> dict[str, Any]:
    """写入版本树节点内容（整段覆盖）。"""
    node_id = str(args.get("node_id", "")).strip()
    content = args.get("content")
    if not node_id:
        return {"error": "node_id 不能为空"}
    if not isinstance(content, dict):
        return {"error": "content 必须是对象"}
    if save_node_content(node_id, content):
        return {"ok": True, "node_id": node_id}
    return {"error": f"节点不存在: {node_id}"}


async def _list_templates(args: dict[str, Any]) -> list[dict[str, Any]]:
    """列出内置简历模板。"""
    return list_templates()


async def _export_pdf(args: dict[str, Any]) -> dict[str, Any]:
    """把节点内容导出为 PDF 文件。"""
    from resume_agent.config import settings

    node_id = str(args.get("node_id", "")).strip()
    template_id = str(args.get("template_id", "modern")) or "modern"
    if not node_id:
        return {"error": "node_id 不能为空"}

    content = get_node_content(node_id)
    if content is None:
        return {"error": f"节点不存在: {node_id}"}
    if not content:
        return {"error": f"节点 {node_id} 内容为空，无法导出"}

    try:
        pdf_bytes = build_pdf(
            resume_data=content,
            job_title=str(args.get("job_title", "")),
            company=str(args.get("company", "")),
            template_id=template_id,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Agent export_pdf 失败: %s", exc)
        return {"error": f"PDF 生成失败: {exc}"}

    export_dir = settings.files_root / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    filename = f"agent_{node_id}_{uuid.uuid4().hex[:8]}.pdf"
    file_path = export_dir / filename
    file_path.write_bytes(pdf_bytes)

    return {"ok": True, "filename": filename, "file_path": str(file_path)}


async def _web_search(args: dict[str, Any]) -> Any:
    """Tavily Web 搜索；未配置时返回提示。"""
    from resume_agent.config import settings

    query = str(args.get("query", "")).strip()
    if not query:
        return {"error": "query 不能为空"}
    if not settings.tavily_api_key:
        return {"results": [], "note": "Tavily 未配置，无法进行 Web 搜索"}
    max_results = args.get("max_results", 5)
    if not isinstance(max_results, int) or max_results < 1 or max_results > 10:
        max_results = 5
    results = search_web(query, max_results=max_results)
    return {"results": results}


async def _ask_user(args: dict[str, Any]) -> Any:
    """ask_user 由 AgentRunner 特判，不应走到这里。"""
    raise RuntimeError(
        "ask_user 必须由 AgentRunner 处理（暂停等待用户输入），不能直接执行"
    )


def build_registry() -> ToolRegistry:
    """构建注册了全部内置工具的注册表。"""
    registry = ToolRegistry()

    registry.register(ToolSpec(
        name="retrieve_knowledge",
        description=(
            "在用户的知识库（上传的周报、项目文档等真实经历素材）中"
            "做语义检索。用于为简历撰写找真实素材，避免编造。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "检索查询词，如「K8s 部署经验」「推荐系统优化」",
                },
                "top_k": {
                    "type": "integer",
                    "description": "返回条数，1-10，默认 3",
                },
            },
            "required": ["query"],
        },
        execute=_retrieve_knowledge,
    ))

    registry.register(ToolSpec(
        name="parse_jd",
        description=(
            "把职位描述（JD）文本解析为结构化字段：职位名、公司、"
            "技术栈、硬技能、软技能、加分项。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "jd_text": {
                    "type": "string",
                    "description": "JD 原文文本",
                },
            },
            "required": ["jd_text"],
        },
        execute=_parse_jd,
    ))

    registry.register(ToolSpec(
        name="analyze_gap",
        description=(
            "对照 JD 结构化数据与知识库，生成技能差距报告："
            "每项技能的覆盖状态（covered/partial/missing）与证据。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "structured_jd": {
                    "type": "object",
                    "description": "parse_jd 输出的结构化 JD 对象",
                },
            },
            "required": ["structured_jd"],
        },
        execute=_analyze_gap,
    ))

    registry.register(ToolSpec(
        name="read_node",
        description="读取版本树某个简历节点（master/branch/company）的完整内容。",
        parameters={
            "type": "object",
            "properties": {
                "node_id": {
                    "type": "string",
                    "description": "节点 ID，如 master / security",
                },
            },
            "required": ["node_id"],
        },
        execute=_read_node,
    ))

    registry.register(ToolSpec(
        name="write_node",
        description=(
            "写入版本树节点的完整简历内容（整段覆盖）。调用后系统会暂停并"
            "向用户展示待写入内容，用户明确确认后才真正写入；被拒绝时"
            "根据用户反馈修改后可再次调用。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "node_id": {
                    "type": "string",
                    "description": "节点 ID",
                },
                "content": {
                    "type": "object",
                    "description": "完整简历内容对象（experience/projects/skills 等）",
                },
            },
            "required": ["node_id", "content"],
        },
        execute=_write_node,
    ))

    registry.register(ToolSpec(
        name="list_templates",
        description="列出可用的简历模板（modern / classic / tech 等）及其说明。",
        parameters={
            "type": "object",
            "properties": {},
        },
        execute=_list_templates,
    ))

    registry.register(ToolSpec(
        name="export_pdf",
        description="把指定节点的简历内容渲染为 PDF 文件。",
        parameters={
            "type": "object",
            "properties": {
                "node_id": {
                    "type": "string",
                    "description": "节点 ID",
                },
                "template_id": {
                    "type": "string",
                    "description": "模板 ID，默认 modern",
                },
                "job_title": {
                    "type": "string",
                    "description": "目标岗位名（可选，用于 PDF 标题）",
                },
                "company": {
                    "type": "string",
                    "description": "目标公司名（可选）",
                },
            },
            "required": ["node_id"],
        },
        execute=_export_pdf,
    ))

    registry.register(ToolSpec(
        name="web_search",
        description="用 Tavily 搜索互联网信息（技术、行业、公司背景等）。",
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索查询词",
                },
                "max_results": {
                    "type": "integer",
                    "description": "返回条数，1-10，默认 5",
                },
            },
            "required": ["query"],
        },
        execute=_web_search,
    ))

    registry.register(ToolSpec(
        name=ASK_USER_TOOL_NAME,
        description=(
            "向用户提问以获取必要信息（如经历细节、澄清需求）。"
            "调用后循环暂停，等待用户回答。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "要问用户的问题",
                },
            },
            "required": ["question"],
        },
        execute=_ask_user,
    ))

    return registry


__all__ = ["build_registry", "ASK_USER_TOOL_NAME", "WRITE_NODE_TOOL_NAME"]
