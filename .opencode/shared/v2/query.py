"""
QUERY 协议：子 Agent → 编排层的数据请求接口。

子 Agent 在写作过程中，如果发现缺少信息，可以通过 QUERY 指令
向编排层请求更多上下文。编排层拦截 QUERY，从 graph 查询，
将结果追加到 session 上下文。

协议格式：
    QUERY: query_type(param1="value1", param2="value2")
    
示例：
    QUERY: character_background(name="林渊")
    QUERY: scene_detail(scene_id="sc_0015")
    QUERY: world_rule(name="灵气淬体")
    QUERY: foreshadowing_status(id="F001")
    QUERY: plot_thread_summary(name="主线")
    QUERY: advanced_search(keywords=["剑", "灵气"], limit=5)
    QUERY: book_knowledge(slug="fanren-xiuxian", topic="power_system")
    QUERY: list_knowledge_books()
"""

from __future__ import annotations

import re
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Pattern


# ── 协议 ──────────────────────────────────────────────────────────────────

@dataclass
class QueryRequest:
    """从子 Agent 输出中解析出的查询请求"""
    query_type: str
    params: Dict[str, Any] = field(default_factory=dict)
    raw_text: str = ""

    def to_prompt_block(self, result: "QueryResult") -> str:
        """将查询结果渲染为 prompt 块（注入到 session 上下文）"""
        lines = []
        lines.append(f"[QUERY RESULT: {self.query_type}]")
        lines.append(f"  Request: {self.raw_text}")
        if result.error:
            lines.append(f"  Error: {result.error}")
        elif result.summary:
            lines.append(f"  {result.summary}")
        if result.content:
            lines.append("")
            lines.append(result.content)
        lines.append("")
        return "\n".join(lines)


@dataclass
class QueryResult:
    """查询结果"""
    success: bool = True
    error: str = ""
    summary: str = ""
    content: str = ""
    data: Optional[Dict[str, Any]] = None
    source_ids: List[str] = field(default_factory=list)  # 来源叙事单元 ID


# ── QUERY 解析器 ──────────────────────────────────────────────────────────

# QUERY 正则: QUERY: type(param1="val1", param2=val2)
QUERY_PATTERN: Pattern = re.compile(
    r"QUERY:\s*(\w+)"                           # type
    r"(?:\(([^)]*)\))?"                          # optional params
)

PARAM_PATTERN: Pattern = re.compile(
    r"""(\w+)\s*=\s*"([^"]*)"                    # key="value"
        |(\w+)\s*=\s*'([^']*)'                   # key='value'
        |(\w+)\s*=\s*(\d+(?:\.\d+)?)             # key=number
        |(\w+)\s*=\s*\[([^\]]*)\]                # key=[list]
        |(\w+)\s*=\s*([^,)\s]+)                  # key=bare_value""",
    re.VERBOSE,
)


def parse_query(text: str) -> Optional[QueryRequest]:
    """
    从文本中解析 QUERY 指令。
    
    如果文本中包含多个 QUERY，只返回第一个。
    返回 None 表示没有有效的 QUERY。
    """
    match = QUERY_PATTERN.search(text)
    if not match:
        return None
    
    type_name = match.group(1)
    params_str = match.group(2)
    
    query_type = type_name
    
    params = {}
    if params_str:
        for pm in PARAM_PATTERN.finditer(params_str):
            key = pm.group(1) or pm.group(3) or pm.group(5) or pm.group(7) or pm.group(9)
            value = pm.group(2) or pm.group(4) or pm.group(6) or pm.group(8) or pm.group(10)
            if value is not None:
                # 列表参数
                if pm.group(8) is not None:
                    params[key] = [v.strip().strip('"') for v in value.split(",") if v.strip()]
                # 数字参数
                elif pm.group(6) is not None:
                    params[key] = float(value) if "." in value else int(value)
                # 字符串参数
                else:
                    params[key] = value
    
    return QueryRequest(
        query_type=query_type,
        params=params,
        raw_text=match.group(0),
    )


def extract_all_queries(text: str) -> List[QueryRequest]:
    """从文本中提取所有 QUERY 指令"""
    queries = []
    for match in QUERY_PATTERN.finditer(text):
        parsed = parse_query(match.group(0))
        if parsed:
            queries.append(parsed)
    return queries


def strip_queries(text: str) -> str:
    """从文本中移除 QUERY 指令（只保留正文）"""
    return QUERY_PATTERN.sub("", text).strip()




