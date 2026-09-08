"""JD 截图分析端点测试。

覆盖：
- MinerUClient 单元测试（mock requests，测试完整 OCR 流程与错误处理）
  - 单文件 ``upload_and_parse`` 流程
  - 多文件 ``upload_and_parse_multiple`` 流程
- JD 分析端点集成测试（mock MinerUClient + LLMClient，测试完整流程）
  - 多文件上传（图片 / PDF / TXT）
  - 不支持的文件格式
  - MinerU API 错误处理
  - LLM 结构化提取（含 markdown 包裹 JSON 场景）

使用 conftest.py 的 ``_isolated_env`` fixture 隔离存储。
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from resume_agent.parsers.mineru_client import MinerUClient, MinerUError

# === 辅助工具 ===


class _MockResponse:
    """模拟 requests.Response。"""

    def __init__(
        self,
        json_data: Any = None,
        status_code: int = 200,
        content: bytes | None = None,
    ) -> None:
        self._json_data = json_data
        self.status_code = status_code
        if content is not None:
            self.content = content
        elif json_data is not None:
            self.content = json.dumps(json_data).encode()
        else:
            self.content = b""

    def json(self) -> Any:
        return self._json_data


def _make_zip_bytes(md_content: str, filename: str = "full.md") -> bytes:
    """构造包含 ``full.md``（或指定文件名）的 zip 字节流。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(filename, md_content)
    return buf.getvalue()


def _make_zip_without_full_md() -> bytes:
    """构造不含 ``full.md`` 的 zip 字节流。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("other.txt", "other content")
    return buf.getvalue()


def _build_mineru_success_mocks(md_content: str) -> MagicMock:
    """构造 MinerU 成功流程的完整 requests mock。

    包含：POST 申请上传链接 → PUT 上传 → GET 轮询（done）→ GET 下载 zip。
    """
    mock_requests = MagicMock()
    mock_requests.post.return_value = _MockResponse(
        {
            "code": 0,
            "data": {
                "batch_id": "batch-123",
                "file_urls": ["https://upload.example.com"],
            },
        }
    )
    mock_requests.put.return_value = _MockResponse(status_code=200)
    zip_bytes = _make_zip_bytes(md_content)
    mock_requests.get.side_effect = [
        # 第一次 GET：轮询，返回 done
        _MockResponse(
            {
                "code": 0,
                "data": {
                    "extract_result": [
                        {
                            "state": "done",
                            "full_zip_url": "https://zip.example.com",
                            "file_name": "screenshot.png",
                        }
                    ]
                },
            }
        ),
        # 第二次 GET：下载 zip
        _MockResponse(content=zip_bytes),
    ]
    return mock_requests


def _build_mineru_multiple_success_mocks(
    file_names: list[str], md_contents: list[str]
) -> MagicMock:
    """构造 MinerU 多文件批量成功流程的 requests mock。

    包含：POST 批量申请上传链接 → PUT 上传 N 次 → GET 轮询（全部 done）→
    GET 下载 zip N 次。
    """
    mock_requests = MagicMock()
    mock_requests.post.return_value = _MockResponse(
        {
            "code": 0,
            "data": {
                "batch_id": "batch-multi",
                "file_urls": [
                    f"https://upload.example.com/{i}" for i in range(len(file_names))
                ],
            },
        }
    )
    mock_requests.put.return_value = _MockResponse(status_code=200)

    # 轮询返回所有文件 done
    extract_results = [
        {
            "state": "done",
            "full_zip_url": f"https://zip.example.com/{i}",
            "file_name": fname,
        }
        for i, fname in enumerate(file_names)
    ]
    get_side_effects: list[_MockResponse] = [
        _MockResponse(
            {
                "code": 0,
                "data": {"extract_result": extract_results},
            }
        )
    ]
    # 每个文件下载一次 zip
    for md in md_contents:
        get_side_effects.append(_MockResponse(content=_make_zip_bytes(md)))

    mock_requests.get.side_effect = get_side_effects
    return mock_requests


# === MinerUClient 单文件单元测试 ===


def test_upload_and_parse_success(tmp_path: Path) -> None:
    """完整 MinerU OCR 流程：申请链接 → 上传 → 轮询 → 下载 zip → 提取 full.md。"""
    md_content = "# 推荐算法工程师\n\n腾讯招聘推荐算法工程师，要求 Python/PyTorch。"
    mock_requests = _build_mineru_success_mocks(md_content)

    file_path = tmp_path / "screenshot.png"
    file_path.write_bytes(b"fake-png-content")

    with patch("resume_agent.parsers.mineru_client.requests", mock_requests):
        client = MinerUClient("test-token", "https://mineru.test")
        result = client.upload_and_parse(file_path)

    assert result == md_content
    # 验证 POST 调用参数
    mock_requests.post.assert_called_once()
    post_kwargs = mock_requests.post.call_args.kwargs
    assert "Authorization" in post_kwargs["headers"]
    assert "Bearer test-token" in post_kwargs["headers"]["Authorization"]
    assert post_kwargs["json"]["model_version"] == "vlm"
    # 验证 PUT 调用
    mock_requests.put.assert_called_once()
    # 验证 GET 调用（轮询 + 下载）
    assert mock_requests.get.call_count == 2


def test_upload_and_parse_token_not_configured(tmp_path: Path) -> None:
    """token 为空时抛出 MinerUError。"""
    file_path = tmp_path / "test.png"
    file_path.write_bytes(b"fake")

    client = MinerUClient("", "https://mineru.test")
    with pytest.raises(MinerUError, match="token 未配置"):
        client.upload_and_parse(file_path)


def test_upload_and_parse_request_upload_url_api_error(tmp_path: Path) -> None:
    """申请上传链接时 API 返回错误码应抛出异常。"""
    mock_requests = MagicMock()
    mock_requests.post.return_value = _MockResponse(
        {"code": 1, "msg": "invalid token"}
    )

    file_path = tmp_path / "test.png"
    file_path.write_bytes(b"fake")

    with patch("resume_agent.parsers.mineru_client.requests", mock_requests):
        client = MinerUClient("test-token")
        with pytest.raises(MinerUError, match="申请上传链接失败"):
            client.upload_and_parse(file_path)


def test_upload_and_parse_request_upload_url_http_error(tmp_path: Path) -> None:
    """申请上传链接时 HTTP 非 200 应抛出异常。"""
    mock_requests = MagicMock()
    mock_requests.post.return_value = _MockResponse(status_code=500)

    file_path = tmp_path / "test.png"
    file_path.write_bytes(b"fake")

    with patch("resume_agent.parsers.mineru_client.requests", mock_requests):
        client = MinerUClient("test-token")
        with pytest.raises(MinerUError, match="HTTP 500"):
            client.upload_and_parse(file_path)


def test_upload_and_parse_empty_file_urls(tmp_path: Path) -> None:
    """file_urls 为空时应抛出异常。"""
    mock_requests = MagicMock()
    mock_requests.post.return_value = _MockResponse(
        {"code": 0, "data": {"batch_id": "batch-123", "file_urls": []}}
    )

    file_path = tmp_path / "test.png"
    file_path.write_bytes(b"fake")

    with patch("resume_agent.parsers.mineru_client.requests", mock_requests):
        client = MinerUClient("test-token")
        with pytest.raises(MinerUError, match="file_urls 为空"):
            client.upload_and_parse(file_path)


def test_upload_and_parse_upload_file_http_error(tmp_path: Path) -> None:
    """上传文件 PUT 失败应抛出异常。"""
    mock_requests = MagicMock()
    mock_requests.post.return_value = _MockResponse(
        {
            "code": 0,
            "data": {
                "batch_id": "batch-123",
                "file_urls": ["https://upload.example.com"],
            },
        }
    )
    mock_requests.put.return_value = _MockResponse(status_code=403)

    file_path = tmp_path / "test.png"
    file_path.write_bytes(b"fake")

    with patch("resume_agent.parsers.mineru_client.requests", mock_requests):
        client = MinerUClient("test-token")
        with pytest.raises(MinerUError, match="上传文件失败"):
            client.upload_and_parse(file_path)


def test_upload_and_parse_task_failed(tmp_path: Path) -> None:
    """解析任务 state=failed 时应抛出异常。"""
    mock_requests = MagicMock()
    mock_requests.post.return_value = _MockResponse(
        {
            "code": 0,
            "data": {
                "batch_id": "batch-123",
                "file_urls": ["https://upload.example.com"],
            },
        }
    )
    mock_requests.put.return_value = _MockResponse(status_code=200)
    mock_requests.get.return_value = _MockResponse(
        {
            "code": 0,
            "data": {
                "extract_result": [
                    {"state": "failed", "err_msg": "OCR failed"}
                ]
            },
        }
    )

    file_path = tmp_path / "test.png"
    file_path.write_bytes(b"fake")

    with patch("resume_agent.parsers.mineru_client.requests", mock_requests):
        client = MinerUClient("test-token")
        with pytest.raises(MinerUError, match="解析任务失败"):
            client.upload_and_parse(file_path)


def test_upload_and_parse_poll_timeout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """轮询超时应抛出异常。"""
    # 缩短轮询参数以加速测试
    monkeypatch.setattr(MinerUClient, "_POLL_INTERVAL", 0)
    monkeypatch.setattr(MinerUClient, "_POLL_TIMEOUT", 0.1)

    mock_requests = MagicMock()
    mock_requests.post.return_value = _MockResponse(
        {
            "code": 0,
            "data": {
                "batch_id": "batch-123",
                "file_urls": ["https://upload.example.com"],
            },
        }
    )
    mock_requests.put.return_value = _MockResponse(status_code=200)
    # 始终返回 running 状态，永远不完成
    mock_requests.get.return_value = _MockResponse(
        {
            "code": 0,
            "data": {"extract_result": [{"state": "running"}]},
        }
    )

    file_path = tmp_path / "test.png"
    file_path.write_bytes(b"fake")

    with patch("resume_agent.parsers.mineru_client.requests", mock_requests):
        client = MinerUClient("test-token")
        with pytest.raises(MinerUError, match="轮询超时"):
            client.upload_and_parse(file_path)


def test_upload_and_parse_poll_http_error(tmp_path: Path) -> None:
    """轮询时 HTTP 错误应抛出异常。"""
    mock_requests = MagicMock()
    mock_requests.post.return_value = _MockResponse(
        {
            "code": 0,
            "data": {
                "batch_id": "batch-123",
                "file_urls": ["https://upload.example.com"],
            },
        }
    )
    mock_requests.put.return_value = _MockResponse(status_code=200)
    mock_requests.get.return_value = _MockResponse(status_code=500)

    file_path = tmp_path / "test.png"
    file_path.write_bytes(b"fake")

    with patch("resume_agent.parsers.mineru_client.requests", mock_requests):
        client = MinerUClient("test-token")
        with pytest.raises(MinerUError, match="查询任务状态失败"):
            client.upload_and_parse(file_path)


def test_upload_and_parse_zip_missing_full_md(tmp_path: Path) -> None:
    """zip 中未找到 full.md 应抛出异常。"""
    mock_requests = MagicMock()
    mock_requests.post.return_value = _MockResponse(
        {
            "code": 0,
            "data": {
                "batch_id": "batch-123",
                "file_urls": ["https://upload.example.com"],
            },
        }
    )
    mock_requests.put.return_value = _MockResponse(status_code=200)
    mock_requests.get.side_effect = [
        _MockResponse(
            {
                "code": 0,
                "data": {
                    "extract_result": [
                        {
                            "state": "done",
                            "full_zip_url": "https://zip.example.com",
                        }
                    ]
                },
            }
        ),
        _MockResponse(content=_make_zip_without_full_md()),
    ]

    file_path = tmp_path / "test.png"
    file_path.write_bytes(b"fake")

    with patch("resume_agent.parsers.mineru_client.requests", mock_requests):
        client = MinerUClient("test-token")
        with pytest.raises(MinerUError, match="未找到 full.md"):
            client.upload_and_parse(file_path)


def test_upload_and_parse_full_md_in_subdirectory(tmp_path: Path) -> None:
    """full.md 位于 zip 子目录中也能正确提取。"""
    md_content = "# JD 内容\n\n子目录中的 full.md。"
    mock_requests = MagicMock()
    mock_requests.post.return_value = _MockResponse(
        {
            "code": 0,
            "data": {
                "batch_id": "batch-123",
                "file_urls": ["https://upload.example.com"],
            },
        }
    )
    mock_requests.put.return_value = _MockResponse(status_code=200)
    zip_bytes = _make_zip_bytes(md_content, filename="auto/subdir/full.md")
    mock_requests.get.side_effect = [
        _MockResponse(
            {
                "code": 0,
                "data": {
                    "extract_result": [
                        {
                            "state": "done",
                            "full_zip_url": "https://zip.example.com",
                        }
                    ]
                },
            }
        ),
        _MockResponse(content=zip_bytes),
    ]

    file_path = tmp_path / "test.png"
    file_path.write_bytes(b"fake")

    with patch("resume_agent.parsers.mineru_client.requests", mock_requests):
        client = MinerUClient("test-token")
        result = client.upload_and_parse(file_path)

    assert result == md_content


def test_download_and_extract_md_http_error() -> None:
    """下载 zip 时 HTTP 错误应抛出异常。"""
    mock_requests = MagicMock()
    mock_requests.get.return_value = _MockResponse(status_code=404)

    client = MinerUClient("test-token")
    with (
        patch("resume_agent.parsers.mineru_client.requests", mock_requests),
        pytest.raises(MinerUError, match="下载 zip 失败"),
    ):
        client._download_and_extract_md("https://zip.example.com")


# === MinerUClient 多文件单元测试 ===


def test_upload_and_parse_multiple_success(tmp_path: Path) -> None:
    """批量上传 2 个文件全部成功，返回 2 段 Markdown 文本。"""
    file_names = ["screenshot1.png", "screenshot2.png"]
    md_contents = [
        "# 第一份 JD\n\n腾讯招聘推荐算法工程师。",
        "# 第二份 JD\n\n阿里招聘前端工程师。",
    ]
    mock_requests = _build_mineru_multiple_success_mocks(file_names, md_contents)

    file_paths = [tmp_path / name for name in file_names]
    for fp in file_paths:
        fp.write_bytes(b"fake-content")

    with patch("resume_agent.parsers.mineru_client.requests", mock_requests):
        client = MinerUClient("test-token", "https://mineru.test")
        results = client.upload_and_parse_multiple(file_paths)

    assert len(results) == 2
    assert results[0] == md_contents[0]
    assert results[1] == md_contents[1]
    # 验证 POST 调用（批量申请链接）
    mock_requests.post.assert_called_once()
    # 验证 PUT 调用（每个文件上传一次）
    assert mock_requests.put.call_count == 2
    # 验证 GET 调用（1 次轮询 + 2 次下载 zip）
    assert mock_requests.get.call_count == 3


def test_upload_and_parse_multiple_empty_list() -> None:
    """空文件列表应返回空列表，不发起任何 API 调用。"""
    mock_requests = MagicMock()
    client = MinerUClient("test-token")

    with patch("resume_agent.parsers.mineru_client.requests", mock_requests):
        results = client.upload_and_parse_multiple([])

    assert results == []
    mock_requests.post.assert_not_called()
    mock_requests.put.assert_not_called()
    mock_requests.get.assert_not_called()


def test_upload_and_parse_multiple_token_not_configured(
    tmp_path: Path,
) -> None:
    """token 为空时抛出 MinerUError。"""
    file_path = tmp_path / "test.png"
    file_path.write_bytes(b"fake")

    client = MinerUClient("", "https://mineru.test")
    with pytest.raises(MinerUError, match="token 未配置"):
        client.upload_and_parse_multiple([file_path])


def test_upload_and_parse_multiple_partial_failure(tmp_path: Path) -> None:
    """2 个文件中 1 个 done 1 个 failed，应抛出异常。"""
    file_names = ["ok.png", "bad.png"]
    mock_requests = MagicMock()
    mock_requests.post.return_value = _MockResponse(
        {
            "code": 0,
            "data": {
                "batch_id": "batch-multi",
                "file_urls": [
                    "https://upload.example.com/0",
                    "https://upload.example.com/1",
                ],
            },
        }
    )
    mock_requests.put.return_value = _MockResponse(status_code=200)
    # 一个 done 一个 failed；side_effect 提供轮询 + done 文件的 zip 下载
    mock_requests.get.side_effect = [
        # 第一次 GET：轮询，返回 1 done 1 failed
        _MockResponse(
            {
                "code": 0,
                "data": {
                    "extract_result": [
                        {
                            "state": "done",
                            "full_zip_url": "https://zip.example.com/0",
                            "file_name": "ok.png",
                        },
                        {
                            "state": "failed",
                            "err_msg": "OCR error",
                            "file_name": "bad.png",
                        },
                    ]
                },
            }
        ),
        # 第二次 GET：下载 ok.png 的 zip（之后处理 bad.png 时抛异常）
        _MockResponse(content=_make_zip_bytes("# ok content")),
    ]

    file_paths = [tmp_path / name for name in file_names]
    for fp in file_paths:
        fp.write_bytes(b"fake-content")

    with patch("resume_agent.parsers.mineru_client.requests", mock_requests):
        client = MinerUClient("test-token")
        with pytest.raises(MinerUError, match="解析失败"):
            client.upload_and_parse_multiple(file_paths)


# === JD 分析端点集成测试 ===


def _init_jd_env() -> None:
    """初始化 JD 测试环境（确保 files_root 存在）。"""
    from resume_agent.config import settings

    settings.files_root.mkdir(parents=True, exist_ok=True)


def _install_mock_mineru(
    monkeypatch: pytest.MonkeyPatch, md_texts: list[str] | str = "# JD\n\n职位描述内容。"
) -> None:
    """mock MinerUClient.upload_and_parse_multiple 返回指定 Markdown 文本。"""
    from resume_agent.api import jd as jd_module

    if isinstance(md_texts, str):
        md_texts = [md_texts]

    def fake_upload_and_parse_multiple(
        self: MinerUClient, file_paths: list[Path]
    ) -> list[str]:
        return md_texts

    monkeypatch.setattr(
        jd_module.MinerUClient,
        "upload_and_parse_multiple",
        fake_upload_and_parse_multiple,
    )


def _install_mock_mineru_error(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    """mock MinerUClient.upload_and_parse_multiple 抛出异常。"""
    from resume_agent.api import jd as jd_module

    def fake_upload_and_parse_multiple(
        self: MinerUClient, file_paths: list[Path]
    ) -> list[str]:
        raise error

    monkeypatch.setattr(
        jd_module.MinerUClient,
        "upload_and_parse_multiple",
        fake_upload_and_parse_multiple,
    )


def _install_mock_llm(
    monkeypatch: pytest.MonkeyPatch, structured: dict[str, Any]
) -> None:
    """mock extract_jd_fields 返回指定结构化字典。"""
    from resume_agent.api import jd as jd_module
    from resume_agent.llm.client import LLMClient

    async def fake_extract(raw_text: str) -> dict[str, Any]:
        return structured

    monkeypatch.setattr(
        LLMClient, "configured", property(lambda self: True)
    )
    monkeypatch.setattr(jd_module, "extract_jd_fields", fake_extract)


def _install_mock_llm_raw(
    monkeypatch: pytest.MonkeyPatch, raw_response: str
) -> None:
    """mock extract_jd_fields 抛解析错误（用于测试非法 JSON 场景）。"""
    from resume_agent.api import jd as jd_module
    from resume_agent.llm.client import LLMClient

    async def fake_extract(raw_text: str) -> dict[str, Any]:
        raise RuntimeError(f"LLM 返回内容无法解析为 JSON: {raw_response}")

    monkeypatch.setattr(
        LLMClient, "configured", property(lambda self: True)
    )
    monkeypatch.setattr(jd_module, "extract_jd_fields", fake_extract)


def test_analyze_success_full_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    """完整 JD 分析流程：上传截图 → MinerU OCR → LLM 结构化提取。"""
    _init_jd_env()
    from resume_agent.config import settings
    from resume_agent.main import app

    md_text = "# 推荐算法工程师\n\n腾讯招聘推荐算法工程师，要求 Python/PyTorch。"
    structured = {
        "job_title": "推荐算法工程师",
        "company": "腾讯",
        "tech_stack": ["Python", "PyTorch"],
        "hard_skills": ["模型训练", "特征工程"],
        "soft_skills": ["跨团队协作"],
        "bonus_items": ["顶会论文", "开源贡献"],
    }
    _install_mock_mineru(monkeypatch, md_text)
    _install_mock_llm(monkeypatch, structured)

    client = TestClient(app)
    response = client.post(
        "/api/jd/analyze",
        files=[("files", ("jd.png", b"fake-png-content", "image/png"))],
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    data = body["data"]
    assert data["raw_text"] == md_text
    assert data["structured"]["job_title"] == "推荐算法工程师"
    assert data["structured"]["company"] == "腾讯"
    assert "Python" in data["structured"]["tech_stack"]
    assert "顶会论文" in data["structured"]["bonus_items"]

    # 验证文件已保存
    jd_dir = settings.files_root / "jd"
    saved_files = list(jd_dir.glob("*.png"))
    assert len(saved_files) == 1


def test_analyze_rejects_unsupported_file_type(monkeypatch: pytest.MonkeyPatch) -> None:
    """不支持的文件格式（xlsx）应返回 INVALID_FILE_TYPE。"""
    _init_jd_env()
    from resume_agent.main import app

    client = TestClient(app)
    response = client.post(
        "/api/jd/analyze",
        files=[("files", ("jd.xlsx", b"fake-xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))],
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "INVALID_FILE_TYPE"


def test_analyze_rejects_gif_format(monkeypatch: pytest.MonkeyPatch) -> None:
    """GIF 格式应被拒绝。"""
    _init_jd_env()
    from resume_agent.main import app

    client = TestClient(app)
    response = client.post(
        "/api/jd/analyze",
        files=[("files", ("jd.gif", b"fake", "image/gif"))],
    )

    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "INVALID_FILE_TYPE"


def test_analyze_accepts_jpg_and_jpeg(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """jpg 和 jpeg 格式应被接受。"""
    _init_jd_env()
    from resume_agent.main import app

    _install_mock_mineru(monkeypatch, "# JD")
    _install_mock_llm(
        monkeypatch,
        {
            "job_title": "工程师",
            "company": "",
            "tech_stack": [],
            "hard_skills": [],
            "soft_skills": [],
            "bonus_items": [],
        },
    )

    client = TestClient(app)
    for ext in ("jpg", "jpeg"):
        response = client.post(
            "/api/jd/analyze",
            files=[("files", (f"jd.{ext}", b"fake", "image/jpeg"))],
        )
        body = response.json()
        assert body["ok"] is True, f"格式 {ext} 应被接受"


def test_analyze_accepts_pdf_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PDF 格式应被接受并经 MinerU 解析。"""
    _init_jd_env()
    from resume_agent.main import app

    md_text = "# PDF JD\n\n来自 PDF 的职位描述。"
    _install_mock_mineru(monkeypatch, md_text)
    _install_mock_llm(
        monkeypatch,
        {
            "job_title": "工程师",
            "company": "",
            "tech_stack": [],
            "hard_skills": [],
            "soft_skills": [],
            "bonus_items": [],
        },
    )

    client = TestClient(app)
    response = client.post(
        "/api/jd/analyze",
        files=[("files", ("jd.pdf", b"fake-pdf", "application/pdf"))],
    )

    body = response.json()
    assert body["ok"] is True
    assert body["data"]["raw_text"] == md_text


def test_analyze_accepts_txt_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TXT 格式应被接受，直接读取文本，不经过 MinerU。"""
    _init_jd_env()
    from resume_agent.api import jd as jd_module
    from resume_agent.main import app

    txt_content = "这是一段纯文本 JD，描述职位要求。"
    # mock MinerU 以确保它不被调用
    def fake_upload_and_parse_multiple(
        self: MinerUClient, file_paths: list[Path]
    ) -> list[str]:
        raise AssertionError("TXT 不应经过 MinerU 解析")

    monkeypatch.setattr(
        jd_module.MinerUClient,
        "upload_and_parse_multiple",
        fake_upload_and_parse_multiple,
    )
    _install_mock_llm(
        monkeypatch,
        {
            "job_title": "工程师",
            "company": "",
            "tech_stack": [],
            "hard_skills": [],
            "soft_skills": [],
            "bonus_items": [],
        },
    )

    client = TestClient(app)
    response = client.post(
        "/api/jd/analyze",
        files=[("files", ("jd.txt", txt_content.encode("utf-8"), "text/plain"))],
    )

    body = response.json()
    assert body["ok"] is True
    assert body["data"]["raw_text"] == txt_content


def test_analyze_multiple_files_merge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """上传 2 张图片，mock MinerU 返回 2 段文本，验证 raw_text 包含两段且用 --- 分隔。"""
    _init_jd_env()
    from resume_agent.main import app

    md_texts = [
        "# 第一段 JD\n\n职位描述上半部分。",
        "# 第二段 JD\n\n职位描述下半部分。",
    ]
    _install_mock_mineru(monkeypatch, md_texts)
    _install_mock_llm(
        monkeypatch,
        {
            "job_title": "工程师",
            "company": "",
            "tech_stack": [],
            "hard_skills": [],
            "soft_skills": [],
            "bonus_items": [],
        },
    )

    client = TestClient(app)
    response = client.post(
        "/api/jd/analyze",
        files=[
            ("files", ("jd1.png", b"fake-png-1", "image/png")),
            ("files", ("jd2.png", b"fake-png-2", "image/png")),
        ],
    )

    body = response.json()
    assert body["ok"] is True
    raw_text = body["data"]["raw_text"]
    assert "第一段 JD" in raw_text
    assert "第二段 JD" in raw_text
    assert "---" in raw_text


def test_analyze_mixed_formats(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """上传 1 张图片 + 1 个 TXT，验证合并文本。"""
    _init_jd_env()
    from resume_agent.main import app

    mineru_md = "# 图片解析结果\n\n来自截图的职位描述。"
    txt_content = "纯文本补充说明。"
    _install_mock_mineru(monkeypatch, mineru_md)
    _install_mock_llm(
        monkeypatch,
        {
            "job_title": "工程师",
            "company": "",
            "tech_stack": [],
            "hard_skills": [],
            "soft_skills": [],
            "bonus_items": [],
        },
    )

    client = TestClient(app)
    response = client.post(
        "/api/jd/analyze",
        files=[
            ("files", ("jd.png", b"fake-png", "image/png")),
            ("files", ("note.txt", txt_content.encode("utf-8"), "text/plain")),
        ],
    )

    body = response.json()
    assert body["ok"] is True
    raw_text = body["data"]["raw_text"]
    assert "图片解析结果" in raw_text
    assert txt_content in raw_text
    assert "---" in raw_text


def test_analyze_mineru_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MinerU 解析失败应返回 PARSE_FAILED。"""
    _init_jd_env()
    from resume_agent.main import app

    _install_mock_mineru_error(monkeypatch, MinerUError("MinerU API token 未配置"))

    client = TestClient(app)
    response = client.post(
        "/api/jd/analyze",
        files=[("files", ("jd.png", b"fake", "image/png"))],
    )

    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "PARSE_FAILED"
    assert "token 未配置" in body["error"]["message"]


def test_analyze_mineru_unexpected_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MinerU 抛出非 MinerUError 异常也应返回 PARSE_FAILED。"""
    _init_jd_env()
    from resume_agent.main import app

    _install_mock_mineru_error(monkeypatch, ConnectionError("网络断开"))

    client = TestClient(app)
    response = client.post(
        "/api/jd/analyze",
        files=[("files", ("jd.png", b"fake", "image/png"))],
    )

    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "PARSE_FAILED"


def test_analyze_llm_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """LLM 未配置时应返回 LLM_NOT_CONFIGURED。"""
    _init_jd_env()
    from resume_agent.llm.client import LLMClient
    from resume_agent.main import app

    _install_mock_mineru(monkeypatch, "# JD text")
    monkeypatch.setattr(
        LLMClient, "configured", property(lambda self: False)
    )

    client = TestClient(app)
    response = client.post(
        "/api/jd/analyze",
        files=[("files", ("jd.png", b"fake", "image/png"))],
    )

    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "LLM_NOT_CONFIGURED"


def test_analyze_llm_extract_failed_invalid_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM 返回非法 JSON 应返回 EXTRACT_FAILED。"""
    _init_jd_env()
    from resume_agent.main import app

    _install_mock_mineru(monkeypatch, "# JD text")
    _install_mock_llm_raw(monkeypatch, "this is not json at all {{{")

    client = TestClient(app)
    response = client.post(
        "/api/jd/analyze",
        files=[("files", ("jd.png", b"fake", "image/png"))],
    )

    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "EXTRACT_FAILED"


def test_analyze_llm_raises_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM 调用抛出异常应返回 EXTRACT_FAILED。"""
    _init_jd_env()
    from resume_agent.api import jd as jd_module
    from resume_agent.main import app

    _install_mock_mineru(monkeypatch, "# JD text")

    from resume_agent.llm.client import LLMClient

    async def fake_extract(raw_text: str) -> dict[str, Any]:
        raise RuntimeError("LLM 调用失败")

    monkeypatch.setattr(
        LLMClient, "configured", property(lambda self: True)
    )
    monkeypatch.setattr(jd_module, "extract_jd_fields", fake_extract)

    client = TestClient(app)
    response = client.post(
        "/api/jd/analyze",
        files=[("files", ("jd.png", b"fake", "image/png"))],
    )

    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "EXTRACT_FAILED"


def test_analyze_llm_structured_extraction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM 结构化提取应返回完整字段。"""
    _init_jd_env()
    from resume_agent.main import app

    md_text = "某公司招聘前端工程师，要求 Vue/React，加分项：开源贡献"
    structured = {
        "job_title": "前端工程师",
        "company": "某公司",
        "tech_stack": ["Vue", "React"],
        "hard_skills": ["前端开发"],
        "soft_skills": ["沟通"],
        "bonus_items": ["开源贡献"],
    }
    _install_mock_mineru(monkeypatch, md_text)
    _install_mock_llm(monkeypatch, structured)

    client = TestClient(app)
    response = client.post(
        "/api/jd/analyze",
        files=[("files", ("screenshot.jpg", b"fake-jpg", "image/jpeg"))],
    )

    body = response.json()
    assert body["ok"] is True
    s = body["data"]["structured"]
    assert s["job_title"] == "前端工程师"
    assert s["company"] == "某公司"
    assert set(s["tech_stack"]) == {"Vue", "React"}
    assert "开源贡献" in s["bonus_items"]
    assert s["hard_skills"] == ["前端开发"]
    assert s["soft_skills"] == ["沟通"]


def test_analyze_llm_returns_markdown_wrapped_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM 返回 markdown 代码块包裹的 JSON 也能正确解析。"""
    _init_jd_env()
    from resume_agent.api import jd as jd_module
    from resume_agent.main import app

    _install_mock_mineru(monkeypatch, "# JD")

    structured = {
        "job_title": "后端工程师",
        "company": "",
        "tech_stack": ["Go"],
        "hard_skills": [],
        "soft_skills": [],
        "bonus_items": [],
    }

    from resume_agent.llm.client import LLMClient

    async def fake_extract(raw_text: str) -> dict[str, Any]:
        return structured

    monkeypatch.setattr(
        LLMClient, "configured", property(lambda self: True)
    )
    monkeypatch.setattr(jd_module, "extract_jd_fields", fake_extract)

    client = TestClient(app)
    response = client.post(
        "/api/jd/analyze",
        files=[("files", ("jd.jpeg", b"fake", "image/jpeg"))],
    )

    body = response.json()
    assert body["ok"] is True
    assert body["data"]["structured"]["job_title"] == "后端工程师"
    assert body["data"]["structured"]["tech_stack"] == ["Go"]


def test_analyze_file_saved_with_uuid_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """上传的文件应以 {uuid}.{ext} 格式保存到 jd 目录。"""
    _init_jd_env()
    from resume_agent.config import settings
    from resume_agent.main import app

    _install_mock_mineru(monkeypatch, "# JD")
    _install_mock_llm(
        monkeypatch,
        {
            "job_title": "测试",
            "company": "",
            "tech_stack": [],
            "hard_skills": [],
            "soft_skills": [],
            "bonus_items": [],
        },
    )

    client = TestClient(app)
    response = client.post(
        "/api/jd/analyze",
        files=[("files", ("my-jd-screenshot.png", b"png-bytes", "image/png"))],
    )

    assert response.status_code == 200
    jd_dir = settings.files_root / "jd"
    saved_files = list(jd_dir.glob("*.png"))
    assert len(saved_files) == 1
    # 文件名应为 uuid 格式（36 字符含连字符）
    saved_name = saved_files[0].stem
    assert len(saved_name) == 36
    assert saved_name.count("-") == 4
    # 内容应与上传的一致
    assert saved_files[0].read_bytes() == b"png-bytes"
