import hashlib
import json
import re
from pathlib import Path

RULESET_VERSION = "2026-11-26"

BLOCKED_TERMS = (
    "破解",
    "外挂",
    "刷单",
    "虚假账号",
    "洗稿",
    "抄袭搬运",
    "绕过风控",
)
AD_TERMS = (
    "国家级",
    "世界级",
    "最佳",
    "最好",
    "第一",
    "唯一",
    "顶级",
    "百分百",
    "绝对有效",
    "永久有效",
    "包治",
    "稳赚不赔",
    "点击即送",
)


def validate_content(
    title: str, body: str, compliance_enabled: bool = True, tags: str = ""
) -> list[dict]:
    if not compliance_enabled:
        return []
    text = f"{title}\n{body}\n{tags}"
    findings = []
    for term in BLOCKED_TERMS:
        if term in text:
            findings.append(
                {"term": term, "type": "prohibited", "message": f"包含禁止发布的内容：{term}"}
            )
    for term in AD_TERMS:
        if term in text:
            findings.append(
                {"term": term, "type": "advertising", "message": f"可能违反广告法用语：{term}"}
            )
    links = re.findall(r"https?://[^\s)]+", text)
    if len(links) > 5:
        findings.append(
            {"term": "", "type": "links", "message": "外链数量较多，请确认符合目标平台规范。"}
        )
    return findings


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def content_fingerprint(
    title: str,
    body: str,
    tags: str = "",
    *,
    rendered_html: str = "",
    media_sha256: str = "",
    media_metadata: dict | None = None,
) -> str:
    payload = {
        "title": title,
        "body": body,
        "tags": tags,
        "rendered_html": rendered_html,
        "media_sha256": media_sha256,
        "media_metadata": media_metadata or {},
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def content_stats(title: str, body: str) -> dict[str, int]:
    clean = re.sub(r"[#>*_`\[\]()\-]", "", body)
    chinese = len(re.findall(r"[\u4e00-\u9fff]", clean))
    words = len(re.findall(r"[A-Za-z0-9]+", clean))
    return {"characters": chinese + words, "readingMinutes": max(1, (chinese + words) // 400)}
