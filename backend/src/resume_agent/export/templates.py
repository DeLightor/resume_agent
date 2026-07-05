"""简历模板配置（US-8）。

定义 ``TemplateConfig`` 数据结构与三套内置模板配置：
``modern`` / ``classic`` / ``tech``。

模板配置为常量，不存数据库，不动态加载，硬编码在本模块。
颜色参考 ``简历模板排版结构分析报告.txt``：
- classic 复刻爆款系列天宫蓝色版（#1C487C）
- tech 紧凑技术风（#0F766E 薄荷绿）
- modern 简洁现代风（#2563eb）
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


# === 三套内置模板配置 ===

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


def list_templates() -> list[dict[str, str]]:
    """返回模板列表，用于 API。

    每项包含 ``id`` / ``name`` / ``description`` / ``theme_color``。

    Returns:
        模板摘要字典列表。
    """
    return [
        {
            "id": cfg.id,
            "name": cfg.name,
            "description": cfg.description,
            "theme_color": cfg.theme_color,
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
