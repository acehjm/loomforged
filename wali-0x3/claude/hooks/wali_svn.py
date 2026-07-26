#!/usr/bin/env python3
"""Stable SVN working-copy boundary shared by WALI hook adapters."""

from __future__ import annotations

import os
import posixpath
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


class SvnBoundaryError(ValueError):
    """Raised when an SVN working-copy boundary cannot be trusted."""


@dataclass(frozen=True)
class SvnStatus:
    """A complete status split into auditable and project-ignored changes."""

    auditable_changes: tuple[tuple[str, str], ...]
    local_only_changes: tuple[tuple[str, str], ...]


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
    """Return complete status while excluding personal client ignore rules."""

    try:
        result = subprocess.run(
            [
                "svn",
                "status",
                "--xml",
                "--no-ignore",
                "--config-option",
                "config:miscellany:global-ignores=",
                ".",
            ],
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


def _relative_status_path(project_root: Path, raw_path: str) -> str:
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = project_root / candidate
    try:
        return candidate.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return posixpath.normpath(raw_path.replace("\\", "/"))


def _property_chain_changed(path: str, property_changes: set[str]) -> bool:
    if "." in property_changes:
        return True
    current = path
    while current not in {"", ".", "/"}:
        if current in property_changes:
            return True
        parent = posixpath.dirname(current)
        current = parent if parent != current else ""
    return False


def classify_status_xml(project_root: Path, status_xml: str) -> SvnStatus:
    """Partition trusted native ignores from changes WALI must audit.

    The XML must come from :func:`read_status_xml`, whose client-level
    ``global-ignores`` override ensures that ``ignored`` means a versioned
    ``svn:ignore`` or ``svn:global-ignores`` property matched the path.
    """

    try:
        root = ET.fromstring(status_xml)
    except ET.ParseError as error:
        raise SvnBoundaryError(f"SVN status XML 无效：{error}") from error

    parsed: list[tuple[str, str, str]] = []
    for entry in root.findall(".//entry"):
        status = entry.find("wc-status")
        if status is None:
            continue
        item = status.get("item", "").lower()
        props = status.get("props", "").lower()
        if item in {"", "normal", "none"} and props not in {
            "",
            "normal",
            "none",
        }:
            item = f"properties-{props}"
        if item in {"", "normal", "none"}:
            continue
        parsed.append(
            (
                _relative_status_path(project_root, entry.get("path", "")),
                item,
                props,
            )
        )

    property_changes = {
        path
        for path, _item, props in parsed
        if props not in {"", "normal", "none"}
    }
    auditable: list[tuple[str, str]] = []
    local_only: list[tuple[str, str]] = []
    for path, item, props in parsed:
        change = (path, item)
        if (
            item == "ignored"
            and props in {"", "normal", "none"}
            and not _property_chain_changed(path, property_changes)
        ):
            local_only.append(change)
        else:
            auditable.append(change)
    return SvnStatus(tuple(auditable), tuple(local_only))
