# -*- coding: utf-8 -*-
"""知识库加载器：始终加载公共域，再加载配置中的业务域。"""

from __future__ import annotations

import os
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
DEFAULT_KNOWLEDGE_DIR = os.path.join(PROJECT_ROOT, "knowledge")


def load_knowledge(config: dict) -> str:
    """加载业务知识、gold cases 和 DDL，返回拼接后的上下文字符串。"""
    kb_dir = config.get("knowledge_dir") or DEFAULT_KNOWLEDGE_DIR
    domains = _resolve_domains(config)
    parts: list[str] = []

    prompt = os.path.join(kb_dir, "AI提示词.md")
    if os.path.isfile(prompt):
        parts.append("=== AI 工作规则 ===\n")
        parts.append(_read(prompt))

    for domain in domains:
        domain_dir = os.path.join(kb_dir, domain)
        if not os.path.isdir(domain_dir):
            continue

        for name, title in (
            ("business-terms.md", "业务术语"),
            ("glossary.md", "业务知识字典"),
            ("gold_cases.md", "黄金案例"),
        ):
            path = os.path.join(domain_dir, name)
            if os.path.isfile(path):
                parts.append(f"\n=== {domain} {title} ===\n")
                parts.append(_read(path))

        ddl_dir = os.path.join(domain_dir, "ddl")
        if os.path.isdir(ddl_dir):
            for fname in sorted(f for f in os.listdir(ddl_dir) if f.endswith(".sql")):
                parts.append(f"\n--- {domain} DDL: {fname} ---\n")
                parts.append(_read(os.path.join(ddl_dir, fname)))

    return "\n".join(parts)


def get_knowledge_info(config: dict) -> dict:
    kb_dir = config.get("knowledge_dir") or DEFAULT_KNOWLEDGE_DIR
    domains = _resolve_domains(config)
    info = {"dir": kb_dir, "domains": domains}

    glossary_count = 0
    ddl_count = 0
    latest_mtime = 0.0
    for domain in domains:
        domain_dir = os.path.join(kb_dir, domain)
        if not os.path.isdir(domain_dir):
            continue
        for fname in ("business-terms.md", "glossary.md", "gold_cases.md"):
            path = os.path.join(domain_dir, fname)
            if os.path.isfile(path):
                glossary_count += 1
                latest_mtime = max(latest_mtime, os.path.getmtime(path))
        ddl_dir = os.path.join(domain_dir, "ddl")
        if os.path.isdir(ddl_dir):
            ddl_files = [f for f in os.listdir(ddl_dir) if f.endswith(".sql")]
            ddl_count += len(ddl_files)
            for fname in ddl_files:
                latest_mtime = max(latest_mtime, os.path.getmtime(os.path.join(ddl_dir, fname)))

    info["glossary_count"] = glossary_count
    info["ddl_count"] = ddl_count
    info["last_updated"] = (
        time.strftime("%Y-%m-%d %H:%M", time.localtime(latest_mtime))
        if latest_mtime
        else "知识库为空"
    )
    return info


def list_domains(config: dict | None = None) -> list[str]:
    kb_dir = (config or {}).get("knowledge_dir") or DEFAULT_KNOWLEDGE_DIR
    if not os.path.isdir(kb_dir):
        return []
    return [
        name
        for name in sorted(os.listdir(kb_dir))
        if os.path.isdir(os.path.join(kb_dir, name))
        and not name.startswith(".")
        and os.path.isfile(os.path.join(kb_dir, name, "glossary.md"))
    ]


def _resolve_domains(config: dict) -> list[str]:
    raw = config.get("domains", ["c_end"])
    if isinstance(raw, str):
        raw = [item.strip() for item in raw.split(",") if item.strip()]
    domains = ["公共"]
    for domain in raw:
        if domain != "公共" and domain not in domains:
            domains.append(domain)
    return domains


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()
