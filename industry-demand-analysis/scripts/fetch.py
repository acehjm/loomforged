#!/usr/bin/env python3
"""
从内部需求系统拉取需求，生成 requirements.jsonl 和 requirements.md。

依赖：
    pip install requests PyYAML

示例：
    python scripts/fetch.py \
      --config config.local.yaml \
      --industry 教育教学 \
      --start 2026-01-01 \
      --end 2026-07-31

按开发流水号查询：
    python scripts/fetch.py \
      --config config.local.yaml \
      --dev-flow KFP20260403009
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
import yaml


class FetchError(RuntimeError):
    """数据拉取或处理失败。"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="从内部需求系统拉取行业需求数据。"
    )

    parser.add_argument(
        "--config",
        default="config.local.yaml",
        help="本地配置文件，默认 config.local.yaml",
    )
    parser.add_argument(
        "--industry",
        help="行业名称，例如：教育教学、煤炭、化工",
    )
    parser.add_argument(
        "--start",
        help="开始日期，格式 YYYY-MM-DD",
    )
    parser.add_argument(
        "--end",
        help="结束日期，格式 YYYY-MM-DD",
    )
    parser.add_argument(
        "--project-name",
        help="项目名称，支持模糊匹配",
    )
    parser.add_argument(
        "--requirement-id",
        help="需求编号",
    )
    parser.add_argument(
        "--dev-flow",
        help="开发流水号",
    )
    parser.add_argument(
        "--product",
        help="产品名称，支持模糊匹配",
    )
    parser.add_argument(
        "--mode",
        choices=("merge", "replace"),
        default="merge",
        help=(
            "merge：与已有数据合并，适用于增量拉取；"
            "replace：覆盖已有数据。默认 merge"
        ),
    )

    return parser.parse_args()


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FetchError(
            f"配置文件不存在：{path}\n"
            "请先复制 config.example.yaml 为 config.local.yaml。"
        )

    try:
        config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise FetchError(f"配置文件格式错误：{exc}") from exc

    for section in ("api", "storage", "processing"):
        if section not in config:
            raise FetchError(f"配置文件缺少节点：{section}")

    return config


def validate_date(value: str | None, field_name: str) -> None:
    if not value:
        return

    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise FetchError(
            f"{field_name}格式错误，应为 YYYY-MM-DD：{value}"
        ) from exc


def to_text_list(value: Any) -> list[str]:
    """
    将接口字段统一转换为文本列表。

    支持字符串、列表和简单对象，方便处理 demandDesc 等不同格式字段。
    """
    if value is None:
        return []

    if isinstance(value, str):
        value = value.strip()
        return [value] if value else []

    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            result.extend(to_text_list(item))
        return result

    if isinstance(value, dict):
        result = []
        for item in value.values():
            result.extend(to_text_list(item))
        return result

    return [str(value)]


def unique_texts(values: list[str]) -> list[str]:
    """
    文本去重。

    比较时忽略连续空白差异，输出时保留原始段落格式。
    """
    result: list[str] = []
    seen: set[str] = set()

    for value in values:
        normalized = re.sub(r"\s+", " ", value).strip()

        if not normalized or normalized in seen:
            continue

        seen.add(normalized)
        result.append(value.strip())

    return result


def collect_fields(
    record: dict[str, Any],
    fields: list[str],
) -> list[str]:
    values: list[str] = []

    for field in fields:
        values.extend(to_text_list(record.get(field)))

    return unique_texts(values)


def contains_text(value: Any, keyword: str | None) -> bool:
    if not keyword:
        return True

    source = " ".join(to_text_list(value)).casefold()
    return keyword.strip().casefold() in source


def parse_record_time(value: Any) -> datetime | None:
    if not value:
        return None

    text = str(value).strip()

    for date_format in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(text[:19], date_format)
        except ValueError:
            continue

    return None


def record_matches(
    record: dict[str, Any],
    args: argparse.Namespace,
) -> bool:
    """
    对接口返回结果再次进行本地过滤。

    即使接口已经支持对应筛选条件，也进行一次本地校验，
    保证最终保存的数据符合用户指定范围。
    """
    if args.industry and not contains_text(
        [
            record.get("industryI18n"),
            record.get("subIndustryI18n"),
        ],
        args.industry,
    ):
        return False

    if args.project_name and not contains_text(
        record.get("projectName"),
        args.project_name,
    ):
        return False

    if args.requirement_id and not contains_text(
        record.get("bizId"),
        args.requirement_id,
    ):
        return False

    if args.dev_flow and not contains_text(
        record.get("devFlowNum"),
        args.dev_flow,
    ):
        return False

    if args.product and not contains_text(
        [
            record.get("produModelName"),
            record.get("produModel"),
            record.get("softName"),
            record.get("productLineI18n"),
            record.get("productSeriesI18n"),
            record.get("components"),
        ],
        args.product,
    ):
        return False

    if args.start or args.end:
        created_at = parse_record_time(record.get("createTime"))

        if created_at is None:
            return False

        if args.start:
            start_date = datetime.strptime(
                args.start,
                "%Y-%m-%d",
            ).date()

            if created_at.date() < start_date:
                return False

        if args.end:
            end_date = datetime.strptime(
                args.end,
                "%Y-%m-%d",
            ).date()

            if created_at.date() > end_date:
                return False

    return True


def build_server_filters(
    field_map: dict[str, Any],
    args: argparse.Namespace,
) -> dict[str, Any]:
    """
    根据 config 中的字段映射生成接口请求参数。

    未配置接口字段的筛选条件将在拉取后进行本地过滤。
    """
    conditions = {
        "industry": args.industry,
        "start_time": args.start,
        "end_time": args.end,
        "project_name": args.project_name,
        "requirement_id": args.requirement_id,
        "development_flow": args.dev_flow,
        "product": args.product,
    }

    result: dict[str, Any] = {}
    local_only: list[str] = []

    for logical_name, value in conditions.items():
        if value is None:
            continue

        api_field = field_map.get(logical_name)

        if api_field:
            result[str(api_field)] = value
        else:
            local_only.append(logical_name)

    if local_only:
        print(
            "以下条件未配置接口字段，将在拉取后进行本地过滤："
            + "、".join(local_only),
            file=sys.stderr,
        )

    return result


def fetch_all(
    config: dict[str, Any],
    args: argparse.Namespace,
) -> list[dict[str, Any]]:
    api_config = config["api"]
    field_map = api_config.get("fields") or {}

    base_url = str(api_config.get("base_url", "")).rstrip("/")
    endpoint = str(api_config.get("endpoint", "")).lstrip("/")

    if not base_url or not endpoint:
        raise FetchError(
            "api.base_url 或 api.endpoint 未配置。"
        )

    cookie_env = str(
        api_config.get("cookie_env", "IRDMS_COOKIE")
    )
    cookie = os.getenv(cookie_env)

    if not cookie:
        raise FetchError(
            f"环境变量 {cookie_env} 未设置。\n"
            f"请先执行：export {cookie_env}='实际 Cookie'"
        )

    headers = {
        str(key): str(value)
        for key, value in (
            api_config.get("headers") or {}
        ).items()
        if value is not None
    }

    headers["Cookie"] = cookie

    page_field = str(
        field_map.get("page") or "page"
    )
    page_size_field = str(
        field_map.get("page_size") or "rows"
    )

    page_size = int(
        api_config.get("page_size", 100)
    )
    timeout = int(
        api_config.get("timeout_seconds", 30)
    )

    request_defaults = dict(
        api_config.get("body_defaults") or {}
    )
    request_defaults.update(
        build_server_filters(field_map, args)
    )

    url = f"{base_url}/{endpoint}"

    records: list[dict[str, Any]] = []
    page = 1

    with requests.Session() as session:
        while True:
            request_body = dict(request_defaults)
            request_body[page_field] = page
            request_body[page_size_field] = page_size

            response = session.post(
                url,
                headers=headers,
                json=request_body,
                timeout=timeout,
                allow_redirects=False,
            )

            if response.status_code in (
                301,
                302,
                303,
                307,
                308,
                401,
                403,
            ):
                raise FetchError(
                    "Cookie 已失效，或当前账号无接口访问权限。"
                )

            response.raise_for_status()

            try:
                payload = response.json()
            except ValueError as exc:
                raise FetchError(
                    "接口未返回 JSON，可能已经跳转到登录页面。"
                ) from exc

            code = payload.get("code")

            if code not in (
                None,
                "000000",
                0,
                "0",
            ):
                message = (
                    payload.get("message")
                    or payload.get("msg")
                    or "未知错误"
                )

                raise FetchError(
                    f"接口返回失败：code={code}，message={message}"
                )

            data = payload.get("data") or {}
            page_records = data.get("list") or []

            if not isinstance(page_records, list):
                raise FetchError(
                    "接口返回格式错误：data.list 不是数组。"
                )

            records.extend(
                item
                for item in page_records
                if isinstance(item, dict)
            )

            print(
                f"第 {page} 页：{len(page_records)} 条，"
                f"累计 {len(records)} 条",
                file=sys.stderr,
            )

            pages = int(data.get("pages") or 0)
            total = int(data.get("total") or 0)

            if not page_records:
                break

            if pages and page >= pages:
                break

            if total and len(records) >= total:
                break

            if not pages and len(page_records) < page_size:
                break

            page += 1

    return records


def generate_fallback_id(
    record: dict[str, Any],
    requirement_content: list[str],
) -> str:
    """
    bizId 缺失时生成稳定标识。

    正常情况下仍优先使用配置中的 unique_key。
    """
    source = json.dumps(
        {
            "project_name": record.get("projectName"),
            "created_at": record.get("createTime"),
            "development_flow": record.get("devFlowNum"),
            "requirement_content": requirement_content,
        },
        ensure_ascii=False,
        sort_keys=True,
    )

    digest = hashlib.sha256(
        source.encode("utf-8")
    ).hexdigest()

    return f"generated-{digest[:16]}"


def normalize_record(
    record: dict[str, Any],
    processing: dict[str, Any],
) -> dict[str, Any]:
    requirement_fields = [
        str(field)
        for field in (
            processing.get("requirement_fields") or []
        )
    ]

    assessment_fields = [
        str(field)
        for field in (
            processing.get("assessment_fields") or []
        )
    ]

    metadata_fields = [
        str(field)
        for field in (
            processing.get("metadata_fields") or []
        )
    ]

    unique_key = str(
        processing.get("unique_key", "bizId")
    )

    requirement_content = collect_fields(
        record,
        requirement_fields,
    )

    assessment_content = collect_fields(
        record,
        assessment_fields,
    )

    record_id = record.get(unique_key)

    if not record_id:
        record_id = generate_fallback_id(
            record,
            requirement_content,
        )

    products = collect_fields(
        record,
        [
            "produModelName",
            "produModel",
            "softName",
            "productLineI18n",
            "productSeriesI18n",
            "components",
        ],
    )

    return {
        "id": str(record_id),
        "project_name": record.get("projectName"),
        "industry": record.get("industryI18n"),
        "region": record.get("areaCodeI18n"),
        "products": products,
        "created_at": record.get("createTime"),
        "development_flow": record.get("devFlowNum"),
        "requirement_content": requirement_content,
        "assessment_content": assessment_content,
        "metadata": {
            field: record.get(field)
            for field in metadata_fields
        },
    }


def read_jsonl(
    path: Path,
) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    records: list[dict[str, Any]] = []

    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        for line_number, line in enumerate(
            file,
            start=1,
        ):
            if not line.strip():
                continue

            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise FetchError(
                    f"{path} 第 {line_number} 行不是有效 JSON。"
                ) from exc

            if isinstance(item, dict):
                records.append(item)

    return records


def merge_records(
    existing: list[dict[str, Any]],
    incoming: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    以 id 为唯一键合并数据。

    同一 id 再次拉取时，以本次接口返回内容覆盖旧数据。
    """
    merged: dict[str, dict[str, Any]] = {}

    for item in existing:
        record_id = str(item.get("id") or "").strip()

        if record_id:
            merged[record_id] = item

    for item in incoming:
        record_id = str(item.get("id") or "").strip()

        if record_id:
            merged[record_id] = item

    return sorted(
        merged.values(),
        key=lambda item: (
            str(item.get("created_at") or ""),
            str(item.get("id") or ""),
        ),
        reverse=True,
    )


def write_jsonl(
    path: Path,
    records: list[dict[str, Any]],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_path = path.with_suffix(
        path.suffix + ".tmp"
    )

    with temporary_path.open(
        "w",
        encoding="utf-8",
        newline="\n",
    ) as file:
        for record in records:
            file.write(
                json.dumps(
                    record,
                    ensure_ascii=False,
                )
            )
            file.write("\n")

    temporary_path.replace(path)


def markdown_value(value: Any) -> str:
    if value in (
        None,
        "",
        [],
    ):
        return "未提供"

    if isinstance(value, list):
        return "、".join(
            str(item)
            for item in value
        )

    return str(value)


def append_content(
    lines: list[str],
    title: str,
    contents: list[str],
) -> None:
    lines.extend(
        [
            f"### {title}",
            "",
        ]
    )

    if not contents:
        lines.extend(
            [
                "_无_",
                "",
            ]
        )
        return

    if len(contents) == 1:
        lines.extend(
            [
                contents[0],
                "",
            ]
        )
        return

    for index, content in enumerate(
        contents,
        start=1,
    ):
        lines.extend(
            [
                f"#### {title} {index}",
                "",
                content,
                "",
            ]
        )


def write_markdown(
    path: Path,
    records: list[dict[str, Any]],
    args: argparse.Namespace,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    lines = [
        "# 行业需求数据",
        "",
        f"- 行业：{args.industry or '未指定'}",
        f"- 时间范围：{args.start or '不限'} 至 {args.end or '不限'}",
        f"- 需求数量：{len(records)}",
        f"- 生成时间：{datetime.now():%Y-%m-%d %H:%M:%S}",
        "",
        "---",
        "",
    ]

    for record in records:
        lines.extend(
            [
                (
                    f"## {markdown_value(record.get('id'))}"
                    f"｜{markdown_value(record.get('project_name'))}"
                ),
                "",
                f"- 行业：{markdown_value(record.get('industry'))}",
                f"- 区域：{markdown_value(record.get('region'))}",
                f"- 产品：{markdown_value(record.get('products'))}",
                f"- 创建时间：{markdown_value(record.get('created_at'))}",
                "",
            ]
        )

        append_content(
            lines,
            "需求内容",
            list(
                record.get("requirement_content")
                or []
            ),
        )

        append_content(
            lines,
            "评估内容",
            list(
                record.get("assessment_content")
                or []
            ),
        )

        lines.extend(
            [
                "---",
                "",
            ]
        )

    temporary_path = path.with_suffix(
        path.suffix + ".tmp"
    )

    temporary_path.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    temporary_path.replace(path)


def safe_path_name(value: str) -> str:
    value = re.sub(
        r'[<>:"/\\|?*\x00-\x1f]',
        "_",
        value.strip(),
    )

    return value or "未指定"


def resolve_output_dir(
    config: dict[str, Any],
    config_path: Path,
    args: argparse.Namespace,
) -> Path:
    root = Path(
        str(
            config["storage"].get(
                "root",
                "./data",
            )
        )
    )

    if not root.is_absolute():
        root = (
            config_path.parent / root
        ).resolve()

    industry = safe_path_name(
        args.industry or "未指定行业"
    )

    if args.start and args.end:
        period = f"{args.start}_{args.end}"
    elif args.start:
        period = f"{args.start}_至今"
    elif args.end:
        period = f"截至_{args.end}"
    else:
        period = "全部时间"

    return (
        root
        / industry
        / safe_path_name(period)
    )


def main() -> int:
    args = parse_args()

    try:
        validate_date(
            args.start,
            "开始日期",
        )
        validate_date(
            args.end,
            "结束日期",
        )

        if (
            args.start
            and args.end
            and args.start > args.end
        ):
            raise FetchError(
                "开始日期不能晚于结束日期。"
            )

        config_path = Path(
            args.config
        ).expanduser().resolve()

        config = load_config(
            config_path
        )

        fetched_records = fetch_all(
            config,
            args,
        )

        filtered_records = [
            record
            for record in fetched_records
            if record_matches(
                record,
                args,
            )
        ]

        normalized_records = [
            normalize_record(
                record,
                config["processing"],
            )
            for record in filtered_records
        ]

        target_dir = resolve_output_dir(
            config,
            config_path,
            args,
        )

        file_config = (
            config["storage"].get("files")
            or {}
        )

        jsonl_path = target_dir / str(
            file_config.get(
                "requirements_jsonl",
                "requirements.jsonl",
            )
        )

        markdown_path = target_dir / str(
            file_config.get(
                "requirements_markdown",
                "requirements.md",
            )
        )

        if args.mode == "merge":
            existing_records = read_jsonl(
                jsonl_path
            )
        else:
            existing_records = []

        final_records = merge_records(
            existing_records,
            normalized_records,
        )

        write_jsonl(
            jsonl_path,
            final_records,
        )

        write_markdown(
            markdown_path,
            final_records,
            args,
        )

        print("")
        print("需求数据拉取完成")
        print(
            f"- 接口返回：{len(fetched_records)} 条"
        )
        print(
            f"- 条件过滤后：{len(filtered_records)} 条"
        )
        print(
            f"- 最终保存：{len(final_records)} 条"
        )
        print(
            f"- JSONL：{jsonl_path}"
        )
        print(
            f"- Markdown：{markdown_path}"
        )

        return 0

    except requests.RequestException as exc:
        print(
            f"请求失败：{exc}",
            file=sys.stderr,
        )
        return 1

    except FetchError as exc:
        print(
            f"错误：{exc}",
            file=sys.stderr,
        )
        return 1

    except KeyboardInterrupt:
        print(
            "操作已取消。",
            file=sys.stderr,
        )
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
