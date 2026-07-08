"""简历模板配置（US-8 + US-16）。

定义 ``TemplateConfig`` 数据结构与六套内置模板配置：
``modern`` / ``classic`` / ``tech`` / ``minimal`` / ``two_column`` / ``academic``。

模板配置为常量，不存数据库，不动态加载，硬编码在本模块。
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass

logger = logging.getLogger("resume_agent")


@dataclass(frozen=True)
class TemplateConfig:
    """单套模板的渲染配置。

    Attributes:
        id: 模板唯一标识，如 ``"modern"``。
        name: 模板中文名称，如 ``"现代简约"``。
        description: 模板简短描述。
        theme_color: 主题色（hex 字符串），用于标题条/分隔线。
        accent_color: 强调色（hex 字符串）。
        section_title_color: 段落标题色（hex 字符串）。
        use_color_block: 是否使用色块标题条（classic=True）。
        margin_mm: 页边距（毫米）。
        font_size_name: 姓名字号。
        font_size_section: 段落标题字号。
        font_size_body: 正文字号。
        columns: 栏数（1 或 2）。
        font_family: 字体族。
        line_height: 行高倍数。
        section_spacing: 段落间距（rem）。
        header_style: 标题风格（"underline" / "color_block" / "minimal" / "academic"）。
    """

    id: str
    name: str
    description: str
    theme_color: str
    accent_color: str
    section_title_color: str
    use_color_block: bool
    margin_mm: float
    font_size_name: int
    font_size_section: int
    font_size_body: int
    # US-16 新增字段
    columns: int = 1
    font_family: str = "system-ui, sans-serif"
    line_height: float = 1.5
    section_spacing: float = 0.75
    header_style: str = "underline"


# === 六套内置模板配置 ===

TEMPLATES: dict[str, TemplateConfig] = {
    "modern": TemplateConfig(
        id="modern",
        name="现代简约",
        description="简洁现代风，分隔线 + 左对齐标题，适合大多数岗位",
        theme_color="#2563eb",
        accent_color="#1a1a1a",
        section_title_color="#1a1a1a",
        use_color_block=False,
        margin_mm=15,
        font_size_name=18,
        font_size_section=11,
        font_size_body=9,
        columns=1,
        font_family="system-ui, sans-serif",
        line_height=1.5,
        section_spacing=0.75,
        header_style="underline",
    ),
    "classic": TemplateConfig(
        id="classic",
        name="经典色块",
        description="复刻爆款系列天宫蓝色版，色块标题条 + 白字标题，沉稳大气",
        theme_color="#1C487C",
        accent_color="#A9886F",
        section_title_color="#1C487C",
        use_color_block=True,
        margin_mm=12.7,
        font_size_name=20,
        font_size_section=12,
        font_size_body=9,
        columns=1,
        font_family="system-ui, sans-serif",
        line_height=1.5,
        section_spacing=0.75,
        header_style="color_block",
    ),
    "tech": TemplateConfig(
        id="tech",
        name="紧凑技术风",
        description="页边距更小、字号更紧凑，技能以标签横排，适合技术岗",
        theme_color="#0F766E",
        accent_color="#0F766E",
        section_title_color="#0F766E",
        use_color_block=False,
        margin_mm=10,
        font_size_name=16,
        font_size_section=10,
        font_size_body=8.5,
        columns=1,
        font_family="system-ui, sans-serif",
        line_height=1.4,
        section_spacing=0.5,
        header_style="underline",
    ),
    "minimal": TemplateConfig(
        id="minimal",
        name="极简白",
        description="单栏大量留白，无色块无分隔线，标题仅加粗，极简美学",
        theme_color="#333333",
        accent_color="#666666",
        section_title_color="#333333",
        use_color_block=False,
        margin_mm=20,
        font_size_name=18,
        font_size_section=11,
        font_size_body=9.5,
        columns=1,
        font_family="system-ui, sans-serif",
        line_height=1.6,
        section_spacing=1.0,
        header_style="minimal",
    ),
    "two_column": TemplateConfig(
        id="two_column",
        name="暖橙卡片风",
        description="暖橙色调，段落以圆角卡片展示，活泼有层次",
        theme_color="#EA580C",
        accent_color="#FB923C",
        section_title_color="#C2410C",
        use_color_block=False,
        margin_mm=12,
        font_size_name=16,
        font_size_section=10,
        font_size_body=8.5,
        columns=1,
        font_family="system-ui, sans-serif",
        line_height=1.5,
        section_spacing=0.6,
        header_style="card",
    ),
    "academic": TemplateConfig(
        id="academic",
        name="学术风",
        description="论文格式，衬线字体，居中标题，适合科研/学术岗位",
        theme_color="#1a1a1a",
        accent_color="#555555",
        section_title_color="#1a1a1a",
        use_color_block=False,
        margin_mm=18,
        font_size_name=16,
        font_size_section=11,
        font_size_body=9,
        columns=1,
        font_family="'Times New Roman', 'Noto Serif SC', serif",
        line_height=1.6,
        section_spacing=0.8,
        header_style="academic",
    ),
}


def get_template(template_id: str) -> TemplateConfig:
    """根据 template_id 获取模板配置。

    未知 id 回退到 ``modern`` 并 log warning，不抛异常，保证向后兼容。

    Args:
        template_id: 模板标识。

    Returns:
        对应的 ``TemplateConfig``，未知 id 返回 ``modern``。
    """
    config = TEMPLATES.get(template_id)
    if config is None:
        logger.warning(
            "未知模板 id: %s，回退到 modern 模板",
            template_id,
        )
        return TEMPLATES["modern"]
    return config


def list_templates() -> list[dict[str, object]]:
    """返回模板列表，用于 API。

    每项包含 ``id`` / ``name`` / ``description`` / ``theme_color`` /
    ``columns`` / ``header_style``。

    Returns:
        模板摘要字典列表。
    """
    return [
        {
            "id": cfg.id,
            "name": cfg.name,
            "description": cfg.description,
            "theme_color": cfg.theme_color,
            "columns": cfg.columns,
            "header_style": cfg.header_style,
        }
        for cfg in TEMPLATES.values()
    ]


def template_config_to_dict(config: TemplateConfig) -> dict[str, object]:
    """将 TemplateConfig 转为字典（便于调试/序列化）。"""
    return asdict(config)


__all__ = [
    "TemplateConfig",
    "TEMPLATES",
    "get_template",
    "list_templates",
    "template_config_to_dict",
]
