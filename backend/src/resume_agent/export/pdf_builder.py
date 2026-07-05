"""ATS 友好 PDF 简历生成器（多模板，US-8）。

使用 reportlab platypus 框架，生成文本可选、可解析的 PDF。
ATS（Applicant Tracking System）友好意味着：
- 文本可选可复制（非图片）
- 清晰的段落结构
- 无复杂表格嵌套

字体：STSong-Light（reportlab 内置 CJK CID 字体，支持中英文）
模板：
- modern：简洁现代风（HRFlowable 分隔线 + 左对齐标题）
- classic：色块标题条（Table 单元格彩色背景 + 白字标题，复刻天宫蓝色版）
- tech：紧凑技术风（小页边距 + 小字号 + 技能标签横排）
"""

from __future__ import annotations

import io
import logging
from typing import Any

from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from resume_agent.export.templates import TemplateConfig, get_template

logger = logging.getLogger("resume_agent")

# 注册 CJK 字体（reportlab 内置，无需额外字体文件）
_FONT_NORMAL = "STSong-Light"
_FONT_BOLD = "STSong-Light"  # CID 字体无 bold 变体，用同字体
# 字体注册标记
_font_registered = False

# 跨模板共享的固定颜色（保证可读性）
_COLOR_PRIMARY = HexColor("#1a1a1a")  # 正文主色
_COLOR_SECONDARY = HexColor("#555555")  # 元信息次色
_COLOR_LIGHT = HexColor("#e5e7eb")  # 分隔线浅灰


def _ensure_font_registered() -> None:
    """注册 CJK CID 字体（仅注册一次）。"""
    global _font_registered
    if not _font_registered:
        from reportlab.pdfbase import pdfmetrics

        pdfmetrics.registerFont(UnicodeCIDFont(_FONT_NORMAL))
        _font_registered = True


def _build_styles(config: TemplateConfig) -> dict[str, ParagraphStyle]:
    """根据模板配置构建段落样式。

    Args:
        config: 模板配置，字号/颜色从 config 读取。

    Returns:
        段落样式字典（name / contact / section_title / job_title /
        job_meta / body / skill）。
    """
    _ensure_font_registered()
    styles = getSampleStyleSheet()

    name_style = ParagraphStyle(
        "ResumeName",
        parent=styles["Title"],
        fontName=_FONT_BOLD,
        fontSize=config.font_size_name,
        textColor=HexColor(config.section_title_color),
        alignment=TA_CENTER,
        spaceAfter=2 * mm,
    )

    contact_style = ParagraphStyle(
        "ResumeContact",
        parent=styles["Normal"],
        fontName=_FONT_NORMAL,
        fontSize=config.font_size_body,
        textColor=_COLOR_SECONDARY,
        alignment=TA_CENTER,
        spaceAfter=4 * mm,
    )

    section_title_style = ParagraphStyle(
        "SectionTitle",
        parent=styles["Heading2"],
        fontName=_FONT_BOLD,
        fontSize=config.font_size_section,
        textColor=HexColor(config.section_title_color),
        spaceBefore=4 * mm,
        spaceAfter=2 * mm,
        borderWidth=0,
        borderPadding=0,
    )

    job_title_style = ParagraphStyle(
        "JobTitle",
        parent=styles["Normal"],
        fontName=_FONT_BOLD,
        fontSize=config.font_size_body + 1,
        textColor=_COLOR_PRIMARY,
        spaceBefore=2 * mm,
        spaceAfter=0.5 * mm,
    )

    job_meta_style = ParagraphStyle(
        "JobMeta",
        parent=styles["Normal"],
        fontName=_FONT_NORMAL,
        fontSize=config.font_size_body,
        textColor=_COLOR_SECONDARY,
        spaceAfter=1 * mm,
    )

    body_style = ParagraphStyle(
        "ResumeBody",
        parent=styles["Normal"],
        fontName=_FONT_NORMAL,
        fontSize=config.font_size_body,
        textColor=_COLOR_PRIMARY,
        leading=config.font_size_body + 3,
        spaceAfter=0.5 * mm,
        leftIndent=4 * mm,
    )

    skill_style = ParagraphStyle(
        "SkillItem",
        parent=styles["Normal"],
        fontName=_FONT_NORMAL,
        fontSize=config.font_size_body,
        textColor=_COLOR_PRIMARY,
        leading=config.font_size_body + 3,
        spaceAfter=0.5 * mm,
        leftIndent=4 * mm,
    )

    return {
        "name": name_style,
        "contact": contact_style,
        "section_title": section_title_style,
        "job_title": job_title_style,
        "job_meta": job_meta_style,
        "body": body_style,
        "skill": skill_style,
    }


def _escape_xml(text: str) -> str:
    """转义 XML 特殊字符（reportlab Paragraph 使用 XML 标记）。"""
    if not text:
        return ""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _build_section_header(
    text: str,
    config: TemplateConfig,
    full_width: float,
) -> list[Any]:
    """构建段落标题 flowable。

    - classic（use_color_block=True）：Table 色块条，白字标题在彩色背景上。
    - modern / tech：Paragraph + HRFlowable 分隔线。

    Args:
        text: 段落标题文本（调用方负责转义）。
        config: 模板配置。
        full_width: 可用内容宽度（pt），用于 classic 色块条宽度。

    Returns:
        flowable 列表。
    """
    _ensure_font_registered()
    base = getSampleStyleSheet()

    if config.use_color_block:
        # classic: 色块标题条
        white_style = ParagraphStyle(
            "SectionTitleBlock",
            parent=base["Heading2"],
            fontName=_FONT_BOLD,
            fontSize=config.font_size_section,
            textColor=white,
            leading=config.font_size_section + 2,
            spaceBefore=0,
            spaceAfter=0,
        )
        table = Table(
            [[Paragraph(text, white_style)]],
            colWidths=[full_width],
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), HexColor(config.theme_color)),
                    ("TEXTCOLOR", (0, 0), (-1, -1), white),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        return [table, Spacer(1, 1 * mm)]

    # modern / tech: Paragraph + HRFlowable
    title_style = ParagraphStyle(
        "SectionTitleInline",
        parent=base["Heading2"],
        fontName=_FONT_BOLD,
        fontSize=config.font_size_section,
        textColor=HexColor(config.section_title_color),
        spaceBefore=4 * mm,
        spaceAfter=2 * mm,
    )
    return [
        Paragraph(text, title_style),
        HRFlowable(width="100%", thickness=0.3, color=_COLOR_LIGHT),
    ]


def _render_skills(
    skills: dict[str, Any],
    config: TemplateConfig,
    styles: dict[str, ParagraphStyle],
) -> list[Any]:
    """渲染技能段落。

    - tech：技能以逗号分隔单行展示（标签横排），更紧凑。
    - modern / classic：逐行展示每个技能。

    Args:
        skills: 技能字典，含 tech_stack / hard_skills / soft_skills。
        config: 模板配置。
        styles: 段落样式字典。

    Returns:
        技能段落 flowable 列表。
    """
    flowables: list[Any] = []
    categories = [
        ("tech_stack", "技术栈"),
        ("hard_skills", "硬技能"),
        ("soft_skills", "软技能"),
    ]
    for category_key, category_label in categories:
        items = skills.get(category_key, [])
        if not items:
            continue

        if config.id == "tech":
            # tech: 逗号分隔单行展示
            parts: list[str] = []
            for item in items:
                if isinstance(item, dict):
                    skill_name = item.get("name", "")
                    context = item.get("context", "")
                    if context:
                        parts.append(f"{skill_name}（{context}）")
                    else:
                        parts.append(skill_name)
                elif isinstance(item, str):
                    parts.append(item)
            line = ", ".join(_escape_xml(p) for p in parts if p)
            if line:
                flowables.append(
                    Paragraph(
                        f"<b>{category_label}:</b> {line}",
                        styles["body"],
                    )
                )
        else:
            # modern / classic: 逐行展示
            for item in items:
                if isinstance(item, dict):
                    skill_name = item.get("name", "")
                    context = item.get("context", "")
                    if context:
                        flowables.append(
                            Paragraph(
                                f"<b>{_escape_xml(skill_name)}</b>: "
                                f"{_escape_xml(context)}",
                                styles["skill"],
                            )
                        )
                    else:
                        flowables.append(
                            Paragraph(_escape_xml(skill_name), styles["skill"]),
                        )
                elif isinstance(item, str):
                    flowables.append(
                        Paragraph(_escape_xml(item), styles["skill"]),
                    )
    return flowables


def build_pdf(
    resume_data: dict[str, Any],
    job_title: str = "",
    company: str = "",
    template_id: str = "modern",
) -> bytes:
    """生成 ATS 友好 PDF（多模板）。

    Args:
        resume_data: 简历数据，包含 experience / projects / skills 等段落。
        job_title: 目标岗位名称（用于标题）。
        company: 目标公司名称。
        template_id: 模板标识（modern / classic / tech），未知 id 回退 modern。

    Returns:
        PDF 文件的二进制内容。
    """
    config = get_template(template_id)
    styles = _build_styles(config)
    buffer = io.BytesIO()

    margin = config.margin_mm * mm
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=margin,
        bottomMargin=margin,
    )
    # 可用内容宽度（用于 classic 色块条 Table 宽度）
    full_width = float(A4[0] - 2 * margin)

    story: list[Any] = []

    # === 标题 ===
    name = resume_data.get("name", "简历")
    story.append(Paragraph(_escape_xml(name), styles["name"]))

    # 联系信息
    contact_parts = []
    if resume_data.get("email"):
        contact_parts.append(resume_data["email"])
    if resume_data.get("phone"):
        contact_parts.append(resume_data["phone"])
    if job_title:
        contact_parts.append(f"目标岗位: {job_title}")
    if contact_parts:
        story.append(
            Paragraph(
                " | ".join(_escape_xml(str(p)) for p in contact_parts),
                styles["contact"],
            )
        )

    story.append(HRFlowable(width="100%", thickness=0.5, color=_COLOR_LIGHT))
    story.append(Spacer(1, 2 * mm))

    # === 工作经历 ===
    experiences = resume_data.get("experience", [])
    if experiences:
        story.extend(_build_section_header("工作经历", config, full_width))
        for exp in experiences:
            company_name = exp.get("company", "")
            role = exp.get("role", "")
            period = exp.get("period", "")
            highlights = exp.get("highlights", [])

            story.append(
                Paragraph(
                    f"{_escape_xml(role)} | {_escape_xml(company_name)}",
                    styles["job_title"],
                )
            )
            if period:
                story.append(
                    Paragraph(_escape_xml(period), styles["job_meta"])
                )
            for h in highlights:
                story.append(
                    Paragraph(f"• {_escape_xml(h)}", styles["body"])
                )

    # === 项目经历 ===
    projects = resume_data.get("projects", [])
    if projects:
        story.append(Spacer(1, 2 * mm))
        story.extend(_build_section_header("项目经历", config, full_width))
        for proj in projects:
            proj_name = proj.get("name", "")
            proj_role = proj.get("role", "")
            proj_period = proj.get("period", "")
            description = proj.get("description", "")
            tech_stack = proj.get("tech_stack", [])

            story.append(
                Paragraph(
                    f"{_escape_xml(proj_name)} | {_escape_xml(proj_role)}",
                    styles["job_title"],
                )
            )
            if proj_period:
                story.append(
                    Paragraph(_escape_xml(proj_period), styles["job_meta"])
                )
            if description:
                story.append(
                    Paragraph(_escape_xml(description), styles["body"])
                )
            if tech_stack:
                story.append(
                    Paragraph(
                        f"<b>技术栈:</b> {_escape_xml(', '.join(tech_stack))}",
                        styles["body"],
                    )
                )

    # === 技能 ===
    skills = resume_data.get("skills", {})
    if skills and isinstance(skills, dict):
        story.append(Spacer(1, 2 * mm))
        story.extend(_build_section_header("技能", config, full_width))
        story.extend(_render_skills(skills, config, styles))

    doc.build(story)
    return buffer.getvalue()


__all__ = ["build_pdf"]
