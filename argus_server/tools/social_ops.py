"""
细化社交操作 - Batch 13 交付

在通用 run_bilibili / run_xhs 之外, 把最常用的"读/互动/发帖"动作包成更明确的 MCP 工具,
帮 Claude 少出错 + 给高风险动作加显式确认参数。

只读 (安全):
    bili_my_dynamics / bili_history / bili_following
    xhs_my_notes / xhs_notifications / xhs_favorites

轻互动 (可逆):
    bili_like(video_id) / bili_triple(video_id)
    xhs_like(note_id) / xhs_comment(note_id, text)

发帖 (有副作用, 需 confirm=True):
    bili_publish_dynamic(text, confirm=False)
    xhs_publish_note(images, title, content, confirm=False)
    xhs_delete_note(note_id, confirm=False)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def _ok(data: Any, **summary) -> Dict:
    return {"success": True, "summary": summary, "data": data}


def _err(message: str, code: str = "SOCIAL_OPS_ERROR", **extra) -> Dict:
    return {"success": False, "error": {"code": code, "message": message, **extra}}


def _require_confirm(action: str) -> Dict:
    return _err(
        f"'{action}' 有副作用 (会真实发出/修改). 再调一次, 传 confirm=True 来确认.",
        code="CONFIRM_REQUIRED",
        action=action,
    )


class SocialOpsTools:
    """bili / xhs 细化操作包装, 底层走 CLIToolsAdapter"""

    def __init__(self, project_root: Optional[str] = None, cli_adapter=None):
        self.project_root = project_root
        self._cli = cli_adapter

    def _require_cli(self) -> Optional[Dict]:
        if self._cli is None:
            return _err("cli 适配器未接入", code="INTERNAL_ERROR")
        return None

    def _require_xhs_ready(self) -> Optional[Dict]:
        err = self._require_cli()
        if err:
            return err

        auth_status = getattr(self._cli, "xhs_auth_status", None)
        if auth_status is None:
            return None

        status_result = auth_status()
        if not status_result.get("success"):
            return status_result

        status_data = status_result.get("data") or {}
        if status_data.get("authenticated"):
            return None

        error = status_data.get("error") or {}
        code = error.get("code")
        if not code:
            code = "NOT_INSTALLED" if not status_data.get("installed") else "AUTH_REQUIRED"
        message = error.get("message") or "xhs CLI 登录态不可用。请先手动刷新小红书登录后重试。"
        return _err(
            message,
            code=code,
            status=status_data.get("status"),
            action_required=status_data.get("action_required"),
            auth_status=status_data,
        )

    def _run_xhs_checked(self, subcommand: str, args: List[str]) -> Dict:
        err = self._require_xhs_ready()
        if err:
            return err
        return self._cli.run_xhs(subcommand, args)

    # ────────────── B 站 只读 ──────────────

    def bili_my_dynamics(self, limit: int = 20) -> Dict:
        err = self._require_cli()
        if err: return err
        return self._cli.run_bilibili("my-dynamics", ["--limit", str(limit)])

    def bili_history(self, limit: int = 30) -> Dict:
        err = self._require_cli()
        if err: return err
        return self._cli.run_bilibili("history", ["--limit", str(limit)])

    def bili_following(self, limit: int = 50) -> Dict:
        err = self._require_cli()
        if err: return err
        return self._cli.run_bilibili("following", ["--limit", str(limit)])

    def bili_feed(self, limit: int = 20) -> Dict:
        err = self._require_cli()
        if err: return err
        return self._cli.run_bilibili("feed", ["--limit", str(limit)])

    def bili_hot(self, limit: int = 30) -> Dict:
        err = self._require_cli()
        if err: return err
        return self._cli.run_bilibili("hot", ["--limit", str(limit)])

    # ────────────── B 站 轻互动 (可逆) ──────────────

    def bili_like(self, video_id: str) -> Dict:
        """点赞 (可再次点同一按钮取消)"""
        err = self._require_cli()
        if err: return err
        if not video_id:
            return _err("video_id 不能为空", code="INVALID_PARAM")
        return self._cli.run_bilibili("like", [video_id])

    def bili_triple(self, video_id: str) -> Dict:
        """一键三连 (点赞 + 投币 + 收藏, 部分不可逆)"""
        err = self._require_cli()
        if err: return err
        if not video_id:
            return _err("video_id 不能为空", code="INVALID_PARAM")
        return self._cli.run_bilibili("triple", [video_id])

    # ────────────── B 站 发帖 (需 confirm) ──────────────

    def bili_publish_dynamic(self, text: str, confirm: bool = False) -> Dict:
        err = self._require_cli()
        if err: return err
        if not text or not text.strip():
            return _err("text 不能为空", code="INVALID_PARAM")
        if not confirm:
            return _require_confirm("bili_publish_dynamic")
        return self._cli.run_bilibili("dynamic-post", ["--text", text])

    def bili_delete_dynamic(self, dynamic_id: str, confirm: bool = False) -> Dict:
        err = self._require_cli()
        if err: return err
        if not dynamic_id:
            return _err("dynamic_id 不能为空", code="INVALID_PARAM")
        if not confirm:
            return _require_confirm("bili_delete_dynamic")
        return self._cli.run_bilibili("dynamic-delete", [dynamic_id])

    # ────────────── 小红书 只读 ──────────────

    def xhs_my_notes(self, limit: int = 20) -> Dict:
        return self._run_xhs_checked("my-notes", ["--limit", str(limit)])

    def xhs_notifications(self, limit: int = 30) -> Dict:
        return self._run_xhs_checked("notifications", ["--limit", str(limit)])

    def xhs_favorites(self, limit: int = 20) -> Dict:
        return self._run_xhs_checked("favorites", ["--limit", str(limit)])

    def xhs_feed(self, limit: int = 20) -> Dict:
        return self._run_xhs_checked("feed", ["--limit", str(limit)])

    def xhs_hot(self, category: Optional[str] = None, limit: int = 30) -> Dict:
        args = ["--limit", str(limit)]
        if category:
            args.extend(["--category", category])
        return self._run_xhs_checked("hot", args)

    def xhs_comments(self, note_id: str, limit: int = 20) -> Dict:
        if not note_id:
            return _err("note_id 不能为空", code="INVALID_PARAM")
        return self._run_xhs_checked("comments", [note_id, "--limit", str(limit)])

    # ────────────── 小红书 轻互动 ──────────────

    def xhs_like(self, note_id: str) -> Dict:
        if not note_id:
            return _err("note_id 不能为空", code="INVALID_PARAM")
        return self._run_xhs_checked("like", [note_id])

    def xhs_favorite(self, note_id: str) -> Dict:
        if not note_id:
            return _err("note_id 不能为空", code="INVALID_PARAM")
        return self._run_xhs_checked("favorite", [note_id])

    def xhs_comment(self, note_id: str, text: str, confirm: bool = False) -> Dict:
        """评论别人的笔记 — 公开可见, 需确认"""
        if not note_id or not text:
            return _err("note_id 和 text 都必需", code="INVALID_PARAM")
        if not confirm:
            return _require_confirm("xhs_comment")
        return self._run_xhs_checked("comment", [note_id, "--text", text])

    # ────────────── 小红书 发帖 / 删除 (需 confirm) ──────────────

    def xhs_publish_note(
        self,
        images: List[str],
        title: str,
        content: str,
        confirm: bool = False,
    ) -> Dict:
        if not images or not isinstance(images, list):
            return _err("images 必须是图片路径列表", code="INVALID_PARAM")
        if not title or not content:
            return _err("title 和 content 都必需", code="INVALID_PARAM")
        if not confirm:
            return _require_confirm("xhs_publish_note")
        args = ["--title", title, "--content", content]
        for img in images:
            args.extend(["--image", img])
        return self._run_xhs_checked("post", args)

    def xhs_delete_note(self, note_id: str, confirm: bool = False) -> Dict:
        if not note_id:
            return _err("note_id 不能为空", code="INVALID_PARAM")
        if not confirm:
            return _require_confirm("xhs_delete_note")
        return self._run_xhs_checked("delete", [note_id])
