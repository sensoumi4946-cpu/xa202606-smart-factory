from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

LLM_ENDPOINT = os.getenv(
    "LLM_ENDPOINT", "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
)
LLM_MODEL = os.getenv("LLM_MODEL", "qwen-plus")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "20"))

ALLOWED_FORMS = ("SELECT", "ASK")
FORBIDDEN = (
    "INSERT",
    "DELETE",
    "DROP",
    "CLEAR",
    "LOAD",
    "CREATE",
    "COPY",
    "MOVE",
    "ADD",
    "SERVICE",
    "WITH",
)
MAX_LIMIT = 200

PREFIXES = """PREFIX sosa: <http://www.w3.org/ns/sosa/>
PREFIX sf:   <http://example.org/smart-factory#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX xsd:  <http://www.w3.org/2001/XMLSchema#>"""


@dataclass
class Translation:
    question: str
    sparql: str
    accepted: bool
    source: str
    violations: list[str] = field(default_factory=list)
    used_properties: list[str] = field(default_factory=list)
    explanation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "sparql": self.sparql,
            "accepted": self.accepted,
            "source": self.source,
            "violations": self.violations,
            "used_properties": self.used_properties,
            "explanation": self.explanation,
        }


def vocabulary(properties: list[str], subsystems: list[str]) -> str:
    return (
        "可用的观测属性 (sosa:ObservableProperty)：\n  "
        + "、".join(properties)
        + "\n可用的子系统 (sf:Subsystem)：\n  "
        + "、".join(subsystems)
    )


def build_prompt(question: str, properties: list[str], subsystems: list[str]) -> str:
    return f"""你是一个把中文运维问题翻译成 SPARQL 查询的助手。

知识图谱使用 SOSA/SSN 本体，观测数据的结构是：
  ?obs a sosa:Observation ;
       sosa:madeBySensor ?sensor ;
       sosa:observedProperty ?prop ;
       sosa:hasSimpleResult ?value ;
       sosa:resultTime ?time .
传感器与子系统的关系：?sensor sf:belongsToSubsystem ?subsystem .
传感器与协议的关系：?sensor sf:transportedVia ?protocol .

{vocabulary(properties, subsystems)}

规则：
1. 只能生成 SELECT 或 ASK 查询，禁止 INSERT/DELETE/DROP/LOAD/SERVICE。
2. 只能使用上面列出的属性和子系统，不要发明新的名字。
3. 必须带 LIMIT，且不超过 {MAX_LIMIT}。
4. 只输出 SPARQL 语句本身，不要解释，不要 markdown 代码块。

问题：{question}"""


def _strip_fences(text: str) -> str:
    text = re.sub(r"^```(?:sparql)?\s*", "", text.strip(), flags=re.IGNORECASE)
    text = re.sub(r"```\s*$", "", text.strip())
    return text.strip()


def _query_form(query: str) -> str:
    body = re.sub(r"PREFIX\s+\S+\s+<[^>]*>", "", query, flags=re.IGNORECASE)
    match = re.search(r"\b(SELECT|ASK|CONSTRUCT|DESCRIBE)\b", body, re.IGNORECASE)
    return match.group(1).upper() if match else ""


def _referenced_properties(query: str, properties: list[str]) -> list[str]:
    lowered = query.lower()
    return [p for p in properties if p.lower() in lowered]


def guard(query: str, properties: list[str], subsystems: list[str]) -> tuple[bool, list[str]]:
    violations: list[str] = []
    if not query.strip():
        return False, ["empty query"]

    upper = query.upper()
    for word in FORBIDDEN:
        if re.search(rf"\b{word}\b", upper):
            violations.append(f"禁止的关键字 {word}")

    form = _query_form(query)
    if form not in ALLOWED_FORMS:
        violations.append(f"只允许 SELECT/ASK，收到 {form or '未知'}")

    if form == "SELECT":
        limits = re.findall(r"\bLIMIT\s+(\d+)", upper)
        if not limits:
            violations.append("缺少 LIMIT")
        elif int(limits[-1]) > MAX_LIMIT:
            violations.append(f"LIMIT {limits[-1]} 超过上限 {MAX_LIMIT}")

    known = {p.lower() for p in properties} | {s.lower() for s in subsystems}
    quoted = re.findall(r'"([^"]{2,40})"', query)
    for token in quoted:
        cleaned = token.strip().lower()
        if cleaned and cleaned.isascii() and cleaned.replace("_", "").isalpha():
            if cleaned not in known:
                violations.append(f"未知词汇 {token}")

    if "sf:measures" in query:
        for match in re.findall(r"sf:measures(\w+)", query):
            snake = re.sub(r"(?<!^)(?=[A-Z])", "_", match).lower()
            if snake not in known:
                violations.append(f"本体中不存在属性 {snake}")

    return not violations, violations


TEMPLATES: list[tuple[str, str, str]] = [
    (
        r"(哪个|哪些).*(子系统|系统).*(告警|报警).*(最多|最频繁)",
        """SELECT ?subsystem (COUNT(?obs) AS ?n) WHERE {{
  ?obs a sosa:Observation ; sosa:madeBySensor ?sensor .
  ?sensor sf:belongsToSubsystem ?subsystem .
}}
GROUP BY ?subsystem
ORDER BY DESC(?n)
LIMIT 20""",
        "按子系统统计观测数量并排序",
    ),
    (
        r"(最近|近期|当前).*(温度|temperature)",
        """SELECT ?sensor ?value ?time WHERE {{
  ?obs a sosa:Observation ;
       sosa:madeBySensor ?sensor ;
       sosa:observedProperty sf:measuresTemperature ;
       sosa:hasSimpleResult ?value ;
       sosa:resultTime ?time .
}}
ORDER BY DESC(?time)
LIMIT 20""",
        "取最近的温度观测",
    ),
    (
        r"(有多少|多少个|几个).*(传感器|设备)",
        """SELECT (COUNT(DISTINCT ?sensor) AS ?n) WHERE {{
  ?obs a sosa:Observation ; sosa:madeBySensor ?sensor .
}}
LIMIT 1""",
        "统计上报过数据的传感器数量",
    ),
    (
        r"(一氧化碳|co).*(超标|最高|最大)",
        """SELECT ?sensor ?value ?time WHERE {{
  ?obs a sosa:Observation ;
       sosa:madeBySensor ?sensor ;
       sosa:observedProperty sf:measuresCo ;
       sosa:hasSimpleResult ?value ;
       sosa:resultTime ?time .
  FILTER(?value > 35)
}}
ORDER BY DESC(?value)
LIMIT 20""",
        "筛选超过阈值的一氧化碳观测",
    ),
]


def from_template(question: str) -> Optional[tuple[str, str]]:
    for pattern, query, explanation in TEMPLATES:
        if re.search(pattern, question, re.IGNORECASE):
            return PREFIXES + "\n\n" + query.format(), explanation
    return None


async def call_llm(prompt: str, client: Optional[httpx.AsyncClient] = None) -> str:
    if not LLM_API_KEY:
        raise RuntimeError("LLM_API_KEY is not set")

    owns = client is None
    active = client if client is not None else httpx.AsyncClient()
    try:
        response = await active.post(
            LLM_ENDPOINT,
            headers={
                "Authorization": f"Bearer {LLM_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": LLM_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
            },
            timeout=LLM_TIMEOUT,
        )
        response.raise_for_status()
        body = response.json()
        return body["choices"][0]["message"]["content"]
    finally:
        if owns:
            await active.aclose()


async def translate(
    question: str,
    properties: list[str],
    subsystems: list[str],
    client: Optional[httpx.AsyncClient] = None,
    allow_llm: bool = True,
) -> Translation:
    template = from_template(question)
    if template is not None:
        sparql, explanation = template
        ok, violations = guard(sparql, properties, subsystems)
        return Translation(
            question=question,
            sparql=sparql,
            accepted=ok,
            source="template",
            violations=violations,
            used_properties=_referenced_properties(sparql, properties),
            explanation=explanation,
        )

    if not allow_llm or not LLM_API_KEY:
        return Translation(
            question=question,
            sparql="",
            accepted=False,
            source="none",
            violations=["无匹配模板，且未配置 LLM_API_KEY"],
        )

    prompt = build_prompt(question, properties, subsystems)
    try:
        raw = await call_llm(prompt, client)
    except Exception as exc:
        return Translation(
            question=question,
            sparql="",
            accepted=False,
            source="llm",
            violations=[f"模型调用失败：{exc}"],
        )

    sparql = _strip_fences(raw)
    if "PREFIX" not in sparql.upper():
        sparql = PREFIXES + "\n\n" + sparql

    ok, violations = guard(sparql, properties, subsystems)
    return Translation(
        question=question,
        sparql=sparql,
        accepted=ok,
        source="llm",
        violations=violations,
        used_properties=_referenced_properties(sparql, properties),
        explanation="由模型生成，已通过本体词汇与只读约束校验" if ok else "已被约束层拦截",
    )
