#!/usr/bin/env python3
"""Stable SVN working-copy boundary shared by WALI hook adapters."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


class SvnBoundaryError(ValueError):
    """Raised when an SVN working-copy boundary cannot be trusted."""


def _has_svn_metadata_at_or_above(project_root: Path) -> bool:
    try:
        current = project_root.resolve()
    except OSError:
        current = project_root.absolute()
    return any(
        (candidate / ".svn").exists()
        for candidate in (current, *current.parents)
    )


def discover_working_copy_root(project_root: Path) -> Path | None:
    """Return the SVN working-copy root, including from a nested directory."""

    try:
        result = subprocess.run(
            ["svn", "info", "--show-item", "wc-root"],
            cwd=project_root,
            capture_output=True,
            check=False,
            text=True,
        )
    except OSError as error:
        if _has_svn_metadata_at_or_above(project_root):
            raise SvnBoundaryError(
                f"存在 .svn 但无法执行 svn info：{error}"
            ) from error
        return None
    if result.returncode != 0 or not result.stdout.strip():
        if _has_svn_metadata_at_or_above(project_root):
            detail = result.stderr.strip() or result.stdout.strip() or "svn info 失败"
            raise SvnBoundaryError(f"存在 .svn 但无法确认工作副本根：{detail}")
        return None
    reported = Path(result.stdout.strip())
    if not reported.is_absolute():
        raise SvnBoundaryError("svn info 返回了非绝对工作副本根路径")
    try:
        return reported.resolve()
    except OSError as error:
        raise SvnBoundaryError(f"无法解析 SVN 工作副本根：{error}") from error


def is_verified_working_copy_root(project_root: Path) -> bool:
    """Return whether ``project_root`` is the writable SVN working-copy root."""

    metadata = project_root / ".svn"
    if not metadata.is_dir() or not os.access(metadata, os.W_OK):
        return False
    try:
        reported_root = discover_working_copy_root(project_root)
    except SvnBoundaryError:
        return False
    return reported_root == project_root.resolve()


def read_status_xml(project_root: Path) -> str:
    """Return the complete local SVN status as XML."""

    try:
        result = subprocess.run(
            ["svn", "status", "--xml", "--no-ignore", "."],
            cwd=project_root,
            capture_output=True,
            check=False,
            text=True,
        )
    except OSError as error:
        raise SvnBoundaryError(f"无法执行 svn status：{error}") from error
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "svn status 失败"
        raise SvnBoundaryError(detail)
    return result.stdout
