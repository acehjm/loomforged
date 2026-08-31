#!/usr/bin/env python3
"""
根据 classified.jsonl 生成行业需求分析报告。

职责：
1. 读取需求分类结果。
2. 按行业、场景、业务、需求和产品进行聚合统计。
3. 识别高频场景、高频业务和高价值需求。
4. 生成报告数据 JSON。
5. 将报告数据注入 HTML 模板，生成独立 HTML 报告。

依赖：
    pip install PyYAML

示例：
    python scripts/report.py \
      --config config.local.yaml \
      --industry 教育教学 \
      --start 2026-01-01 \
      --end 2026-07-31

指定分类文件：
    python scripts/report.py \
      --config config.local.yaml \
      --input data/教育教学/2026-01-01_2026-07-31/classified.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml


class ReportError(RuntimeError):
    """报告数据处理或文件生成失败。"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="根据 classified.jsonl 生成行业需求分析 HTML 报告。"
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
        "--input",
        help="classified.jsonl 文件路径；未指定时根据行业和时间范围自动定位",
    )
    parser.add_argument(
        "--output",
        help="HTML 报告输出路径；未指定时根据配置自动生成",
    )
    parser.add_argument(
        "--title",
        help="报告标题；未指定时使用配置中的 report.title",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=20,
        help="排名类数据最多保留多少项，默认 20",
    )
    parser.add_argument(
        "--high-value-min-count",
        type=int,
        default=2,
        help="高价值需求最少出现次数，默认 2",
    )

    return parser.parse_args()


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ReportError(
            f"配置文件不存在：{path}\n"
            "请先复制 config.example.yaml 为 config.local.yaml。"
        )

    try:
        config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ReportError(f"配置文件格式错误：{exc}") from exc

    for section in ("storage", "templates", "report"):
        if section not in config:
            raise ReportError(f"配置文件缺少节点：{section}")

    return config


def validate_date(value: str | None, field_name: str) -> None:
    if not value:
        return

    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ReportError(
            f"{field_name}格式错误，应为 YYYY-MM-DD：{value}"
        ) from exc


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise ReportError(f"分类数据文件不存在：{path}")

    records: list[dict[str, Any]] = []

    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue

            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ReportError(
                    f"{path} 第 {line_number} 行不是有效 JSON。"
                ) from exc

            if isinstance(item, dict):
                records.append(item)

    if not records:
        raise ReportError(f"分类数据文件为空：{path}")

    return records


def to_text(value: Any) -> str:
    if value is None:
        return ""

    if isinstance(value, str):
        return value.strip()

    if isinstance(value, (int, float, bool)):
        return str(value)

    if isinstance(value, list):
        return "、".join(
            text
            for item in value
            if (text := to_text(item))
        )

    if isinstance(value, dict):
        return "、".join(
            text
            for item in value.values()
            if (text := to_text(item))
        )

    return str(value).strip()


def to_text_list(value: Any) -> list[str]:
    if value is None:
        return []

    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []

    if isinstance(value, list):
        result: list[str] = []

        for item in value:
            result.extend(to_text_list(item))

        return unique_texts(result)

    if isinstance(value, dict):
        result: list[str] = []

        for item in value.values():
            result.extend(to_text_list(item))

        return unique_texts(result)

    return [str(value)]


def unique_texts(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()

    for value in values:
        text = str(value).strip()
        normalized = normalize_key(text)

        if not normalized or normalized in seen:
            continue

        seen.add(normalized)
        result.append(text)

    return result


def normalize_key(value: str) -> str:
    """
    生成用于去重和归并的文本键。

    Classify 阶段应尽量统一 summary、scene 和 business 的表达。
    这里仅处理空白和常见标点差异，不进行语义猜测。
    """
    value = value.casefold().strip()
    value = re.sub(r"\s+", "", value)
    value = re.sub(r"[，。；：、,.!?！？:;（）()\[\]【】]", "", value)
    return value


def parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None

    text = str(value).strip()

    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        pass

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


def is_in_date_range(
    value: Any,
    start: date | None,
    end: date | None,
) -> bool:
    if start is None and end is None:
        return True

    parsed = parse_datetime(value)

    if parsed is None:
        return False

    current = parsed.date()

    if start and current < start:
        return False

    if end and current > end:
        return False

    return True


def contains_text(value: Any, keyword: str | None) -> bool:
    if not keyword:
        return True

    source = to_text(value).casefold()
    return keyword.strip().casefold() in source


def first_value(
    record: dict[str, Any],
    *keys: str,
) -> Any:
    for key in keys:
        value = record.get(key)

        if value not in (None, "", [], {}):
            return value

    return None


def normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    """
    将不同版本的 classified.jsonl 字段统一为报告使用结构。

    Classify 阶段应保留原始记录的基础信息，例如：
    id、project_name、industry、products、created_at。
    """
    record_id = first_value(
        record,
        "id",
        "requirement_id",
        "bizId",
    )

    project_name = first_value(
        record,
        "project_name",
        "projectName",
    )

    industry = first_value(
        record,
        "industry",
        "industryI18n",
    )

    created_at = first_value(
        record,
        "created_at",
        "createTime",
    )

    development_flow = first_value(
        record,
        "development_flow",
        "devFlowNum",
    )

    scene = to_text_list(
        first_value(
            record,
            "scene",
            "scenes",
        )
    )

    business = to_text_list(
        first_value(
            record,
            "business",
            "businesses",
        )
    )

    products = to_text_list(
        first_value(
            record,
            "products",
            "product",
            "components",
        )
    )

    objects = to_text_list(
        first_value(
            record,
            "objects",
            "business_objects",
        )
    )

    requirement_types = to_text_list(
        first_value(
            record,
            "requirement_type",
            "requirement_types",
        )
    )

    summary = to_text(
        first_value(
            record,
            "normalized_demand",
            "demand",
            "summary",
        )
    )

    confidence = to_text(
        first_value(
            record,
            "confidence",
        )
    ).lower()

    evidence = first_value(
        record,
        "evidence",
    )

    inference = to_text_list(
        first_value(
            record,
            "inference",
        )
    )

    questions = to_text_list(
        first_value(
            record,
            "questions",
        )
    )

    requirement_content = to_text_list(
        first_value(
            record,
            "requirement_content",
            "requirements",
        )
    )

    assessment_content = to_text_list(
        first_value(
            record,
            "assessment_content",
            "assessments",
        )
    )

    return {
        "id": to_text(record_id) or "未提供",
        "project_name": to_text(project_name) or "未提供",
        "industry": to_text(industry) or "未分类",
        "created_at": to_text(created_at),
        "development_flow": to_text(development_flow),
        "scene": scene,
        "business": business,
        "products": products,
        "objects": objects,
        "requirement_type": requirement_types,
        "summary": summary,
        "confidence": confidence or "unknown",
        "evidence": evidence,
        "inference": inference,
        "questions": questions,
        "requirement_content": requirement_content,
        "assessment_content": assessment_content,
        "raw": record,
    }


def safe_path_name(value: str) -> str:
    value = re.sub(
        r'[<>:"/\\|?*\x00-\x1f]',
        "_",
        value.strip(),
    )

    return value or "未指定"


def period_name(
    start: str | None,
    end: str | None,
) -> str:
    if start and end:
        return f"{start}_{end}"

    if start:
        return f"{start}_至今"

    if end:
        return f"截至_{end}"

    return "全部时间"


def resolve_relative_path(
    config_path: Path,
    value: str,
) -> Path:
    path = Path(value).expanduser()

    if path.is_absolute():
        return path

    return (config_path.parent / path).resolve()


def resolve_input_path(
    config: dict[str, Any],
    config_path: Path,
    args: argparse.Namespace,
) -> Path:
    if args.input:
        return Path(args.input).expanduser().resolve()

    if not args.industry:
        raise ReportError(
            "未指定 --input 时，必须通过 --industry 指定行业。"
        )

    storage = config["storage"]
    root = resolve_relative_path(
        config_path,
        str(storage.get("root", "./data")),
    )

    files = storage.get("files") or {}
    classified_name = str(
        files.get(
            "classified_jsonl",
            "classified.jsonl",
        )
    )

    return (
        root
        / safe_path_name(args.industry)
        / safe_path_name(
            period_name(args.start, args.end)
        )
        / classified_name
    )


def resolve_template_path(
    config: dict[str, Any],
    config_path: Path,
) -> Path:
    template_value = str(
        config["templates"].get(
            "report",
            "./templates/report.html",
        )
    )

    template_path = resolve_relative_path(
        config_path,
        template_value,
    )

    if not template_path.exists():
        raise ReportError(
            f"HTML 报告模板不存在：{template_path}"
        )

    return template_path


def resolve_output_paths(
    config: dict[str, Any],
    config_path: Path,
    args: argparse.Namespace,
    industry: str,
) -> tuple[Path, Path]:
    if args.output:
        html_path = Path(args.output).expanduser().resolve()
    else:
        report_root = resolve_relative_path(
            config_path,
            str(
                config["storage"].get(
                    "reports",
                    "./reports",
                )
            ),
        )

        filename = (
            f"{safe_path_name(industry)}-"
            f"{safe_path_name(period_name(args.start, args.end))}-"
            "demand-analysis.html"
        )

        html_path = report_root / filename

    data_path = html_path.with_suffix(".json")

    return html_path, data_path


def count_item(
    store: dict[str, dict[str, Any]],
    name: str,
    record: dict[str, Any],
) -> None:
    """
    为场景、业务或产品累计需求、项目和关联信息。
    """
    item = store.setdefault(
        name,
        {
            "name": name,
            "requirement_ids": set(),
            "projects": set(),
            "products": set(),
            "scenes": set(),
            "businesses": set(),
            "examples": [],
        },
    )

    item["requirement_ids"].add(record["id"])

    if record["project_name"] != "未提供":
        item["projects"].add(record["project_name"])

    item["products"].update(record["products"])
    item["scenes"].update(record["scene"])
    item["businesses"].update(record["business"])

    if len(item["examples"]) < 5:
        item["examples"].append(
            {
                "id": record["id"],
                "project_name": record["project_name"],
                "summary": record["summary"],
            }
        )


def serialize_ranked_items(
    store: dict[str, dict[str, Any]],
    top_n: int,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []

    for item in store.values():
        result.append(
            {
                "name": item["name"],
                "count": len(item["requirement_ids"]),
                "project_count": len(item["projects"]),
                "product_count": len(item["products"]),
                "projects": sorted(item["projects"]),
                "products": sorted(item["products"]),
                "scenes": sorted(item["scenes"]),
                "businesses": sorted(item["businesses"]),
                "examples": item["examples"],
            }
        )

    result.sort(
        key=lambda item: (
            -item["count"],
            -item["product_count"],
            -item["project_count"],
            item["name"],
        )
    )

    return result[:top_n]


def aggregate_high_value_demands(
    records: list[dict[str, Any]],
    top_n: int,
    min_count: int,
) -> list[dict[str, Any]]:
    """
    按 Classify 阶段归一化后的 summary 聚合具体需求。

    如果 summary 表达没有在 Classify 阶段完成统一，
    相近需求可能仍会被拆分统计。
    """
    groups: dict[str, dict[str, Any]] = {}

    for record in records:
        summary = record["summary"].strip()

        if not summary:
            continue

        key = normalize_key(summary)

        if not key:
            continue

        group = groups.setdefault(
            key,
            {
                "name": summary,
                "requirement_ids": set(),
                "projects": set(),
                "products": set(),
                "scenes": set(),
                "businesses": set(),
                "examples": [],
            },
        )

        group["requirement_ids"].add(record["id"])

        if record["project_name"] != "未提供":
            group["projects"].add(record["project_name"])

        group["products"].update(record["products"])
        group["scenes"].update(record["scene"])
        group["businesses"].update(record["business"])

        if len(group["examples"]) < 5:
            group["examples"].append(
                {
                    "id": record["id"],
                    "project_name": record["project_name"],
                    "created_at": record["created_at"],
                }
            )

    result: list[dict[str, Any]] = []

    for group in groups.values():
        count = len(group["requirement_ids"])

        if count < min_count:
            continue

        result.append(
            {
                "name": group["name"],
                "count": count,
                "project_count": len(group["projects"]),
                "product_count": len(group["products"]),
                "projects": sorted(group["projects"]),
                "products": sorted(group["products"]),
                "scenes": sorted(group["scenes"]),
                "businesses": sorted(group["businesses"]),
                "examples": group["examples"],
            }
        )

    result.sort(
        key=lambda item: (
            -item["count"],
            -item["product_count"],
            -item["project_count"],
            item["name"],
        )
    )

    return result[:top_n]


def build_scene_business_tree(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    生成“场景 → 业务 → 需求 → 产品”关系数据。
    """
    tree: dict[str, dict[str, Any]] = {}

    for record in records:
        scenes = record["scene"] or ["未分类"]
        businesses = record["business"] or ["未分类"]

        for scene_name in scenes:
            scene = tree.setdefault(
                scene_name,
                {
                    "name": scene_name,
                    "requirement_ids": set(),
                    "products": set(),
                    "businesses": {},
                },
            )

            scene["requirement_ids"].add(record["id"])
            scene["products"].update(record["products"])

            for business_name in businesses:
                business = scene["businesses"].setdefault(
                    business_name,
                    {
                        "name": business_name,
                        "requirement_ids": set(),
                        "products": set(),
                        "demands": Counter(),
                    },
                )

                business["requirement_ids"].add(record["id"])
                business["products"].update(record["products"])

                if record["summary"]:
                    business["demands"][record["summary"]] += 1

    result: list[dict[str, Any]] = []

    for scene in tree.values():
        businesses: list[dict[str, Any]] = []

        for business in scene["businesses"].values():
            demands = [
                {
                    "name": name,
                    "count": count,
                }
                for name, count in business["demands"].most_common()
            ]

            businesses.append(
                {
                    "name": business["name"],
                    "count": len(business["requirement_ids"]),
                    "products": sorted(business["products"]),
                    "demands": demands,
                }
            )

        businesses.sort(
            key=lambda item: (
                -item["count"],
                item["name"],
            )
        )

        result.append(
            {
                "name": scene["name"],
                "count": len(scene["requirement_ids"]),
                "products": sorted(scene["products"]),
                "businesses": businesses,
            }
        )

    result.sort(
        key=lambda item: (
            -item["count"],
            item["name"],
        )
    )

    return result


def build_monthly_trend(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()

    for record in records:
        created_at = parse_datetime(record["created_at"])

        if created_at is None:
            continue

        counter[created_at.strftime("%Y-%m")] += 1

    return [
        {
            "period": period,
            "count": counter[period],
        }
        for period in sorted(counter)
    ]


def build_data_quality(
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    total = len(records)

    missing_scene = sum(
        1
        for record in records
        if not record["scene"]
    )
    missing_business = sum(
        1
        for record in records
        if not record["business"]
    )
    missing_summary = sum(
        1
        for record in records
        if not record["summary"]
    )
    missing_products = sum(
        1
        for record in records
        if not record["products"]
    )

    confidence = Counter(
        record["confidence"] or "unknown"
        for record in records
    )

    def ratio(value: int) -> float:
        if total == 0:
            return 0.0

        return round(value / total, 4)

    return {
        "total": total,
        "missing_scene": missing_scene,
        "missing_scene_ratio": ratio(missing_scene),
        "missing_business": missing_business,
        "missing_business_ratio": ratio(missing_business),
        "missing_summary": missing_summary,
        "missing_summary_ratio": ratio(missing_summary),
        "missing_products": missing_products,
        "missing_products_ratio": ratio(missing_products),
        "confidence": dict(confidence),
    }


def build_representative_requirements(
    records: list[dict[str, Any]],
    limit: int = 20,
) -> list[dict[str, Any]]:
    sorted_records = sorted(
        records,
        key=lambda item: (
            parse_datetime(item["created_at"])
            or datetime.min
        ),
        reverse=True,
    )

    result: list[dict[str, Any]] = []

    for record in sorted_records[:limit]:
        result.append(
            {
                "id": record["id"],
                "project_name": record["project_name"],
                "created_at": record["created_at"],
                "scene": record["scene"],
                "business": record["business"],
                "summary": record["summary"],
                "products": record["products"],
                "objects": record["objects"],
                "requirement_type": record["requirement_type"],
                "confidence": record["confidence"],
                "requirement_content": record["requirement_content"],
                "assessment_content": record["assessment_content"],
            }
        )

    return result


def build_findings(
    scene_rankings: list[dict[str, Any]],
    business_rankings: list[dict[str, Any]],
    product_rankings: list[dict[str, Any]],
    high_value_demands: list[dict[str, Any]],
) -> list[str]:
    """
    只生成基于统计结果的事实性摘要，不进行超出数据的推断。
    """
    findings: list[str] = []

    if scene_rankings:
        item = scene_rankings[0]
        findings.append(
            f"需求数量最多的场景是“{item['name']}”，"
            f"共关联 {item['count']} 条需求。"
        )

    if business_rankings:
        item = business_rankings[0]
        findings.append(
            f"需求数量最多的业务是“{item['name']}”，"
            f"共关联 {item['count']} 条需求。"
        )

    if product_rankings:
        item = product_rankings[0]
        findings.append(
            f"关联需求最多的产品是“{item['name']}”，"
            f"共关联 {item['count']} 条需求。"
        )

    if high_value_demands:
        item = high_value_demands[0]
        findings.append(
            f"出现频率最高的具体需求是“{item['name']}”，"
            f"出现 {item['count']} 次，涉及 "
            f"{item['product_count']} 个产品。"
        )

    return findings


def build_report_data(
    records: list[dict[str, Any]],
    industry: str,
    start: str | None,
    end: str | None,
    top_n: int,
    high_value_min_count: int,
) -> dict[str, Any]:
    scene_store: dict[str, dict[str, Any]] = {}
    business_store: dict[str, dict[str, Any]] = {}
    product_store: dict[str, dict[str, Any]] = {}
    type_counter: Counter[str] = Counter()
    project_names: set[str] = set()
    product_names: set[str] = set()
    dates: list[datetime] = []

    for record in records:
        if record["project_name"] != "未提供":
            project_names.add(record["project_name"])

        product_names.update(record["products"])

        parsed_date = parse_datetime(record["created_at"])

        if parsed_date:
            dates.append(parsed_date)

        for scene in record["scene"] or ["未分类"]:
            count_item(
                scene_store,
                scene,
                record,
            )

        for business in record["business"] or ["未分类"]:
            count_item(
                business_store,
                business,
                record,
            )

        for product in record["products"] or ["未关联产品"]:
            count_item(
                product_store,
                product,
                record,
            )

        for requirement_type in record["requirement_type"]:
            type_counter[requirement_type] += 1

    scene_rankings = serialize_ranked_items(
        scene_store,
        top_n,
    )
    business_rankings = serialize_ranked_items(
        business_store,
        top_n,
    )
    product_rankings = serialize_ranked_items(
        product_store,
        top_n,
    )

    high_value_demands = aggregate_high_value_demands(
        records,
        top_n,
        high_value_min_count,
    )

    actual_start = (
        min(dates).strftime("%Y-%m-%d")
        if dates
        else None
    )
    actual_end = (
        max(dates).strftime("%Y-%m-%d")
        if dates
        else None
    )

    return {
        "meta": {
            "industry": industry,
            "requested_start": start,
            "requested_end": end,
            "actual_start": actual_start,
            "actual_end": actual_end,
            "generated_at": datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
        },
        "overview": {
            "requirement_count": len(records),
            "project_count": len(project_names),
            "product_count": len(product_names),
            "scene_count": len(scene_store),
            "business_count": len(business_store),
        },
        "findings": build_findings(
            scene_rankings,
            business_rankings,
            product_rankings,
            high_value_demands,
        ),
        "monthly_trend": build_monthly_trend(records),
        "scene_rankings": scene_rankings,
        "business_rankings": business_rankings,
        "product_rankings": product_rankings,
        "requirement_type_rankings": [
            {
                "name": name,
                "count": count,
            }
            for name, count in type_counter.most_common(top_n)
        ],
        "scene_business_tree": build_scene_business_tree(records),
        "high_value_demands": high_value_demands,
        "representative_requirements": (
            build_representative_requirements(
                records,
                limit=min(top_n, 20),
            )
        ),
        "data_quality": build_data_quality(records),
    }


def write_json(
    path: Path,
    data: dict[str, Any],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_path = path.with_suffix(
        path.suffix + ".tmp"
    )

    temporary_path.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    temporary_path.replace(path)


def render_html(
    template_path: Path,
    output_path: Path,
    title: str,
    language: str,
    report_data: dict[str, Any],
) -> None:
    template = template_path.read_text(
        encoding="utf-8"
    )

    required_placeholder = "{{REPORT_DATA_JSON}}"

    if required_placeholder not in template:
        raise ReportError(
            "HTML 模板缺少占位符：{{REPORT_DATA_JSON}}"
        )

    report_json = json.dumps(
        report_data,
        ensure_ascii=False,
        separators=(",", ":"),
    )

    # 防止数据文本中的 </script> 提前结束脚本标签。
    report_json = report_json.replace(
        "</",
        "<\\/",
    )

    html = template
    html = html.replace(
        "{{REPORT_TITLE}}",
        title,
    )
    html = html.replace(
        "{{REPORT_LANGUAGE}}",
        language,
    )
    html = html.replace(
        required_placeholder,
        report_json,
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_path = output_path.with_suffix(
        output_path.suffix + ".tmp"
    )

    temporary_path.write_text(
        html,
        encoding="utf-8",
    )

    temporary_path.replace(output_path)


def infer_industry(
    records: list[dict[str, Any]],
    requested_industry: str | None,
) -> str:
    if requested_industry:
        return requested_industry

    counter = Counter(
        record["industry"]
        for record in records
        if record["industry"]
        and record["industry"] != "未分类"
    )

    if not counter:
        return "未指定行业"

    return counter.most_common(1)[0][0]


def filter_records(
    records: list[dict[str, Any]],
    industry: str | None,
    start: str | None,
    end: str | None,
) -> list[dict[str, Any]]:
    start_date = (
        datetime.strptime(
            start,
            "%Y-%m-%d",
        ).date()
        if start
        else None
    )

    end_date = (
        datetime.strptime(
            end,
            "%Y-%m-%d",
        ).date()
        if end
        else None
    )

    result: list[dict[str, Any]] = []

    for record in records:
        if industry and not contains_text(
            record["industry"],
            industry,
        ):
            continue

        if not is_in_date_range(
            record["created_at"],
            start_date,
            end_date,
        ):
            continue

        result.append(record)

    return result


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
            raise ReportError(
                "开始日期不能晚于结束日期。"
            )

        if args.top <= 0:
            raise ReportError(
                "--top 必须大于 0。"
            )

        if args.high_value_min_count <= 0:
            raise ReportError(
                "--high-value-min-count 必须大于 0。"
            )

        config_path = Path(
            args.config
        ).expanduser().resolve()

        config = load_config(
            config_path
        )

        input_path = resolve_input_path(
            config,
            config_path,
            args,
        )

        raw_records = read_jsonl(
            input_path
        )

        normalized_records = [
            normalize_record(record)
            for record in raw_records
        ]

        filtered_records = filter_records(
            normalized_records,
            args.industry,
            args.start,
            args.end,
        )

        if not filtered_records:
            raise ReportError(
                "没有找到符合行业和时间条件的分类数据。"
            )

        industry = infer_industry(
            filtered_records,
            args.industry,
        )

        report_data = build_report_data(
            filtered_records,
            industry,
            args.start,
            args.end,
            args.top,
            args.high_value_min_count,
        )

        template_path = resolve_template_path(
            config,
            config_path,
        )

        html_path, data_path = resolve_output_paths(
            config,
            config_path,
            args,
            industry,
        )

        report_config = config.get("report") or {}

        title = (
            args.title
            or str(
                report_config.get(
                    "title",
                    "行业需求分析报告",
                )
            )
        )

        language = str(
            report_config.get(
                "language",
                "zh-CN",
            )
        )

        write_json(
            data_path,
            report_data,
        )

        render_html(
            template_path,
            html_path,
            title,
            language,
            report_data,
        )

        print("行业需求分析报告生成完成")
        print(f"- 行业：{industry}")
        print(
            f"- 参与分析：{len(filtered_records)} 条需求"
        )
        print(
            f"- 场景数量："
            f"{report_data['overview']['scene_count']}"
        )
        print(
            f"- 业务数量："
            f"{report_data['overview']['business_count']}"
        )
        print(
            f"- 报告数据：{data_path}"
        )
        print(
            f"- HTML 报告：{html_path}"
        )

        return 0

    except ReportError as exc:
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
