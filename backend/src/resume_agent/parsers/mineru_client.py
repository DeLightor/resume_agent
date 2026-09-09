"""MinerU 文档解析 API 客户端。

封装 MinerU 云端文档解析 API 的完整调用流程：

1. ``POST /api/v4/file-urls/batch`` 申请上传链接，返回 ``batch_id`` 与 ``file_urls``。
2. ``PUT {file_url}`` 直接上传文件二进制内容（不设 ``Content-Type``）。
3. ``GET /api/v4/extract-results/batch/{batch_id}`` 轮询任务状态，间隔 2s、超时 120s。
4. 当 ``state == "done"`` 时，从 ``full_zip_url`` 下载 zip，提取 ``full.md``。

使用 ``requests`` 库（同步），不依赖 ``httpx``。

对齐 design.md / US-4 JD 截图分析。
"""

from __future__ import annotations

import io
import time
import zipfile
from pathlib import Path
from typing import Any

import requests


class MinerUError(Exception):
    """MinerU API 调用异常。"""


class MinerUClient:
    """MinerU 文档解析 API 客户端。

    封装「申请上传链接 → 上传文件 → 轮询任务 → 下载 zip → 提取 full.md」完整流程。

    Attributes:
        token: MinerU API Bearer Token。
        base_url: MinerU API 基地址，默认 ``https://mineru.net``。
    """

    # 轮询配置
    _POLL_INTERVAL: int = 2  # 轮询间隔（秒）
    _POLL_TIMEOUT: int = 120  # 轮询超时（秒）
    # HTTP 超时
    _HTTP_TIMEOUT: int = 30

    def __init__(self, token: str, base_url: str = "https://mineru.net") -> None:
        """初始化 MinerU 客户端。

        Args:
            token: MinerU API Bearer Token，为空表示未配置。
            base_url: MinerU API 基地址，末尾 ``/`` 会被自动去除。
        """
        self.token = token
        self.base_url = base_url.rstrip("/")

    # === 公开方法 ===

    def upload_and_parse(self, file_path: Path) -> str:
        """完整流程封装：上传文件并解析为 Markdown 文本。

        流程：
        1. 申请上传链接，拿到 ``batch_id`` 与 ``upload_url``。
        2. PUT 上传文件二进制内容。
        3. 轮询 batch 任务状态，直到全部完成（done / failed）或超时。
        4. 下载结果 zip，提取 ``full.md`` 文本。

        Args:
            file_path: 待解析文件路径（图片 / PDF）。

        Returns:
            ``full.md`` 的 Markdown 文本内容。

        Raises:
            MinerUError: token 未配置、API 返回错误、轮询超时或解析任务失败。
        """
        if not self.token:
            raise MinerUError("MinerU API token 未配置")

        batch_id, upload_url = self._request_upload_url(file_path.name)
        self._upload_file(upload_url, file_path)
        results = self._poll_batch_result(batch_id)

        # 找到 state=done 的结果
        for result in results:
            if result.get("state") == "done":
                zip_url = result.get("full_zip_url")
                if not zip_url:
                    raise MinerUError("任务完成但未返回 full_zip_url")
                return self._download_and_extract_md(zip_url)

        # 检查是否有失败的任务
        for result in results:
            if result.get("state") == "failed":
                err_msg = result.get("err_msg", "未知错误")
                raise MinerUError(f"MinerU 解析任务失败: {err_msg}")

        # 轮询超时（任务仍在运行中）
        raise MinerUError("轮询超时：任务未在规定时间内完成")

    def upload_and_parse_multiple(self, file_paths: list[Path]) -> list[str]:
        """批量上传并解析多个文件。

        使用 MinerU batch API 一次性上传多个文件（≤50），轮询任务状态，
        返回每个文件的 full.md 内容列表（顺序与输入一致）。

        Args:
            file_paths: 待解析文件路径列表。

        Returns:
            每个文件的 Markdown 文本列表。

        Raises:
            MinerUError: token 未配置、API 错误、轮询超时或解析失败。
        """
        if not self.token:
            raise MinerUError("MinerU API token 未配置")
        if not file_paths:
            return []

        filenames = [fp.name for fp in file_paths]
        batch_id, upload_urls = self._request_upload_urls_batch(filenames)

        for url, fp in zip(upload_urls, file_paths, strict=False):
            self._upload_file(url, fp)

        results = self._poll_batch_result(batch_id)

        # 按 file_name 匹配结果，fallback 按索引匹配
        result_by_name: dict[str, dict[str, Any]] = {}
        unnamed_results: list[dict[str, Any]] = []
        for r in results:
            fname = r.get("file_name")
            if fname:
                result_by_name[fname] = r
            else:
                unnamed_results.append(r)

        md_texts: list[str] = []
        unnamed_idx = 0
        for fp in file_paths:
            result = result_by_name.get(fp.name)
            if result is None and unnamed_idx < len(unnamed_results):
                result = unnamed_results[unnamed_idx]
                unnamed_idx += 1
            if result is None:
                raise MinerUError(f"文件 {fp.name} 未在解析结果中找到")

            state = result.get("state")
            if state == "done":
                zip_url = result.get("full_zip_url")
                if not zip_url:
                    raise MinerUError(f"文件 {fp.name} 完成但未返回 full_zip_url")
                md_texts.append(self._download_and_extract_md(zip_url))
            elif state == "failed":
                err_msg = result.get("err_msg", "未知错误")
                raise MinerUError(f"文件 {fp.name} 解析失败: {err_msg}")
            else:
                raise MinerUError(f"文件 {fp.name} 轮询超时: state={state}")

        return md_texts

    def _request_upload_urls_batch(
        self, filenames: list[str]
    ) -> tuple[str, list[str]]:
        """批量申请上传链接。

        ``POST /api/v4/file-urls/batch``，请求体指定多个文件名。

        Args:
            filenames: 文件名列表。

        Returns:
            ``(batch_id, [upload_url, ...])`` 元组。

        Raises:
            MinerUError: HTTP 错误或业务码非 0。
        """
        url = f"{self.base_url}/api/v4/file-urls/batch"
        payload: dict[str, Any] = {
            "files": [{"name": name} for name in filenames],
            "model_version": "vlm",
        }
        response = requests.post(
            url, json=payload, headers=self._headers(), timeout=self._HTTP_TIMEOUT
        )
        if response.status_code != 200:
            raise MinerUError(f"申请上传链接失败: HTTP {response.status_code}")
        data = response.json()
        if data.get("code") != 0:
            raise MinerUError(
                f"申请上传链接失败: {data.get('msg', '未知错误')}"
            )
        batch_id = data["data"]["batch_id"]
        file_urls = data["data"]["file_urls"]
        if not file_urls:
            raise MinerUError("申请上传链接返回的 file_urls 为空")
        return batch_id, file_urls

    # === 内部方法 ===

    def _headers(self) -> dict[str, str]:
        """构造请求头。"""
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def _request_upload_url(self, filename: str) -> tuple[str, str]:
        """申请上传链接。

        ``POST /api/v4/file-urls/batch``，请求体指定文件名与模型版本。

        Args:
            filename: 文件名（用于 MinerU 标识）。

        Returns:
            ``(batch_id, upload_url)`` 元组。

        Raises:
            MinerUError: HTTP 错误或业务码非 0。
        """
        url = f"{self.base_url}/api/v4/file-urls/batch"
        payload: dict[str, Any] = {
            "files": [{"name": filename}],
            "model_version": "vlm",
        }
        response = requests.post(
            url, json=payload, headers=self._headers(), timeout=self._HTTP_TIMEOUT
        )
        if response.status_code != 200:
            raise MinerUError(f"申请上传链接失败: HTTP {response.status_code}")
        data = response.json()
        if data.get("code") != 0:
            raise MinerUError(
                f"申请上传链接失败: {data.get('msg', '未知错误')}"
            )
        batch_id = data["data"]["batch_id"]
        file_urls = data["data"]["file_urls"]
        if not file_urls:
            raise MinerUError("申请上传链接返回的 file_urls 为空")
        return batch_id, file_urls[0]

    def _upload_file(self, upload_url: str, file_path: Path) -> None:
        """PUT 上传文件二进制内容。

        注意：不设 ``Content-Type``，直接以 ``data`` 传输文件流。

        Args:
            upload_url: 上传目标 URL。
            file_path: 本地文件路径。

        Raises:
            MinerUError: 上传失败（HTTP 非 200/201）。
        """
        with file_path.open("rb") as f:
            response = requests.put(upload_url, data=f, timeout=120)
        if response.status_code not in (200, 201):
            raise MinerUError(
                f"上传文件失败: HTTP {response.status_code}"
            )

    def _poll_batch_result(self, batch_id: str) -> list[dict[str, Any]]:
        """轮询 batch 任务状态。

        ``GET /api/v4/extract-results/batch/{batch_id}``，间隔 ``_POLL_INTERVAL``
        秒，超时 ``_POLL_TIMEOUT`` 秒。当所有任务 ``state`` 为 ``done`` 或
        ``failed`` 时返回。

        Args:
            batch_id: MinerU 批次 ID。

        Returns:
            ``extract_result`` 列表，每项含 ``state``、``full_zip_url`` 等字段。

        Raises:
            MinerUError: HTTP 错误或业务码非 0。
        """
        url = f"{self.base_url}/api/v4/extract-results/batch/{batch_id}"
        deadline = time.monotonic() + self._POLL_TIMEOUT
        last_results: list[dict[str, Any]] = []

        while time.monotonic() < deadline:
            response = requests.get(
                url, headers=self._headers(), timeout=self._HTTP_TIMEOUT
            )
            if response.status_code != 200:
                raise MinerUError(
                    f"查询任务状态失败: HTTP {response.status_code}"
                )
            data = response.json()
            if data.get("code") != 0:
                raise MinerUError(
                    f"查询任务状态失败: {data.get('msg', '未知错误')}"
                )
            results = data.get("data", {}).get("extract_result", [])
            last_results = results
            if results and all(
                r.get("state") in ("done", "failed") for r in results
            ):
                return results
            time.sleep(self._POLL_INTERVAL)

        return last_results

    def _download_and_extract_md(self, zip_url: str) -> str:
        """下载 zip 并提取 ``full.md``。

        Args:
            zip_url: 结果 zip 下载地址。

        Returns:
            ``full.md`` 的 UTF-8 文本内容。

        Raises:
            MinerUError: 下载失败、zip 损坏或未找到 ``full.md``。
        """
        response = requests.get(zip_url, timeout=120)
        if response.status_code != 200:
            raise MinerUError(f"下载 zip 失败: HTTP {response.status_code}")

        try:
            with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
                for info in zf.infolist():
                    if Path(info.filename).name == "full.md":
                        return zf.read(info).decode("utf-8")
        except zipfile.BadZipFile as exc:
            raise MinerUError(f"zip 文件损坏: {exc}") from exc

        raise MinerUError("zip 中未找到 full.md")


__all__ = ["MinerUClient", "MinerUError"]
