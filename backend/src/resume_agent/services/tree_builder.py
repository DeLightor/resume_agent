"""版本树构建服务。

上传简历后，将结构化简历数据写入方向（branch）节点的 content_json，
不创建公司节点（简历中通常不含应聘公司信息）。

同时对齐 US-12：将 basic 字段映射为 personal_info 写入节点，
供左栏个人信息表单读取和编辑。
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from resume_agent.db.connection import get_connection
from resume_agent.parsers.extractor import StructuredResume

# 方向 → branch 显示标题映射
_DIRECTION_TITLES: dict[str, str] = {
    "安全": "安全岗方向",
    "算法": "算法岗方向",
    "后端": "后端岗方向",
    "前端": "前端岗方向",
    "数据": "数据岗方向",
    "产品": "产品岗方向",
    "其他": "其他方向",
}


class TreeBuilder:
    """根据结构化简历数据更新版本树方向节点。

    每次调用 ``build_from_resume`` 会：
    1. 确保 Master 节点存在；
    2. 查找或创建 primary_direction 对应的 branch 节点；
    3. 将结构化简历写入 branch 节点的 content_json；
    4. 将 basic + education 映射为 personal_info 写入 content_json。
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = db_path

    def build_from_resume(self, resume: StructuredResume) -> dict[str, Any]:
        """将结构化简历写入方向节点。

        Args:
            resume: 已提取的结构化简历数据。

        Returns:
            包含 ``node``（branch 节点信息）与 ``deduplicated`` 的字典。
        """
        with get_connection(self.db_path) as conn:
            self._ensure_master(conn)
            branch_node = self._find_or_create_branch(conn, resume.primary_direction)

            # 构造 content_json：结构化简历 + personal_info
            content = resume.model_dump()
            content["personal_info"] = self._map_to_personal_info(resume)
            content_json = json.dumps(content, ensure_ascii=False)

            # 更新 branch 节点
            conn.execute(
                """
                UPDATE resume_versions
                SET content_json = ?, updated_at = datetime('now')
                WHERE node_id = ?
                """,
                (content_json, branch_node["node_id"]),
            )

            node = self._fetch_node(conn, branch_node["node_id"])
            return {"node": node, "deduplicated": False}

    def _map_to_personal_info(self, resume: StructuredResume) -> dict[str, Any]:
        """将 StructuredResume 的 basic + education 映射为 personal_info 格式。

        对齐 US-12 的 PersonalInfo schema。
        """
        basic = resume.basic
        return {
            "contact": {
                "name": basic.name or "",
                "gender": basic.gender or "",
                "birth_date": basic.birth_date or "",
                "phone": basic.phone or "",
                "email": basic.email or "",
                "location": basic.location or "",
                "website": basic.website or "",
                "github": basic.github or "",
                "linkedin": basic.linkedin or "",
            },
            "job_intention": {
                "target_role": "",
                "expected_salary": "",
                "availability": "",
            },
            "education": [
                {
                    "school": e.school or "",
                    "degree": e.degree or "",
                    "major": e.major or "",
                    "period": e.period or "",
                }
                for e in resume.education
            ],
            "summary": "",
        }

    # === 内部辅助方法 ===

    def _ensure_master(self, conn: Any) -> str:
        """确保 Master 节点存在，返回其 node_id。"""
        row: dict[str, Any] | None = conn.execute(
            "SELECT node_id FROM resume_versions WHERE node_id = ?",
            ("master",),
        ).fetchone()
        if row is not None:
            return row["node_id"]

        master_id = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO resume_versions (id, node_id, parent_id, node_type, title)
            VALUES (?, ?, NULL, ?, ?)
            """,
            (master_id, "master", "master", "Master 主干"),
        )
        return "master"

    def _find_or_create_branch(
        self, conn: Any, direction: str
    ) -> dict[str, Any]:
        """查找或创建 branch 节点，返回节点字典。"""
        row: dict[str, Any] | None = conn.execute(
            "SELECT * FROM resume_versions WHERE node_type = ? AND direction = ?",
            ("branch", direction),
        ).fetchone()
        if row is not None:
            return row

        title = _DIRECTION_TITLES.get(direction, f"{direction}方向")
        node_id = f"branch-{direction}"
        node_uuid = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO resume_versions (id, node_id, parent_id, node_type, title, direction)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (node_uuid, node_id, "master", "branch", title, direction),
        )
        return {
            "id": node_uuid,
            "node_id": node_id,
            "parent_id": "master",
            "node_type": "branch",
            "title": title,
            "direction": direction,
            "content_json": None,
            "company": None,
        }

    def _fetch_node(self, conn: Any, node_id: str) -> dict[str, Any]:
        """查询单个节点。"""
        row: dict[str, Any] = conn.execute(
            "SELECT * FROM resume_versions WHERE node_id = ?",
            (node_id,),
        ).fetchone()
        return row


__all__ = ["TreeBuilder"]
