"""模板配置测试：US-16。"""

from __future__ import annotations

from resume_agent.export.templates import TEMPLATES, get_template, list_templates


def test_six_templates() -> None:
    """应有 6 套模板。"""
    assert len(TEMPLATES) == 6
    ids = set(TEMPLATES.keys())
    assert ids == {"modern", "classic", "tech", "minimal", "two_column", "academic"}


def test_list_templates_returns_six() -> None:
    """API 返回 6 套模板。"""
    items = list_templates()
    assert len(items) == 6
    for item in items:
        assert "id" in item
        assert "name" in item
        assert "description" in item
        assert "theme_color" in item
        assert "columns" in item
        assert "header_style" in item


def test_get_template_unknown_fallback() -> None:
    """未知模板回退到 modern。"""
    cfg = get_template("nonexistent")
    assert cfg.id == "modern"


def test_new_templates_have_valid_configs() -> None:
    """新模板配置有效。"""
    minimal = get_template("minimal")
    assert minimal.header_style == "minimal"
    assert minimal.margin_mm == 20
    assert minimal.columns == 1

    two_col = get_template("two_column")
    assert two_col.columns == 1
    assert two_col.header_style == "card"

    academic = get_template("academic")
    assert academic.header_style == "academic"
    assert "serif" in academic.font_family


def test_existing_templates_have_new_fields() -> None:
    """旧模板也有新字段。"""
    modern = get_template("modern")
    assert modern.columns == 1
    assert modern.font_family != ""
    assert modern.line_height > 0
    assert modern.section_spacing > 0
    assert modern.header_style == "underline"
