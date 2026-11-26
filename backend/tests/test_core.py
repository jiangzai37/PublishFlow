from app.core.compliance.validator import (
    content_fingerprint,
    content_stats,
    file_sha256,
    validate_content,
)
from app.core.typesetting.engine import plain_text_from_html, render_article
from app.core.typesetting.presets import load_presets


def test_compliance_blocks_prohibited_content():
    findings = validate_content("正常标题", "这里介绍如何洗稿搬运")
    assert any(item["type"] == "prohibited" for item in findings)


def test_compliance_detects_advertising_and_can_be_disabled():
    findings = validate_content("行业第一", "百分百有效")
    assert len(findings) >= 2
    assert validate_content("行业第一", "百分百有效", False) == []


def test_render_article_sanitizes_scripts_and_preserves_structure():
    html = render_article(
        "测试标题",
        "## 小节\n\n正文<script>alert(1)</script>\n\n> 引用",
        "fresh",
        "/media/cover.png",
    )
    assert "<script>" not in html
    assert "测试标题" in html
    assert "<h2" in html
    assert "<blockquote" in html
    assert "cover.png" in html


def test_presets_are_available():
    presets = load_presets()
    assert {preset["id"] for preset in presets} >= {"fresh", "editorial"}


def test_plain_text_conversion():
    text = plain_text_from_html("<h1>标题</h1><p>第一段<br>第二行</p>")
    assert "标题" in text
    assert "第一段" in text
    assert "第二行" in text
    assert "<" not in text


def test_content_stats():
    stats = content_stats("标题", "中文内容 english words")
    assert stats["characters"] > 4
    assert stats["readingMinutes"] >= 1


def test_content_fingerprint_covers_rendered_content_and_media(tmp_path):
    baseline = content_fingerprint("标题", "正文", "标签", rendered_html="<p>正文</p>")
    assert baseline == content_fingerprint("标题", "正文", "标签", rendered_html="<p>正文</p>")
    assert baseline != content_fingerprint(
        "标题", "正文", "标签", rendered_html="<p>正文</p><footer>尾块</footer>"
    )
    assert baseline != content_fingerprint(
        "标题", "正文", "标签", rendered_html="<p>正文</p>", media_sha256="changed"
    )
    assert content_fingerprint("a\nb", "c") != content_fingerprint("a", "b\nc")

    media = tmp_path / "cover.png"
    media.write_bytes(b"first")
    first_hash = file_sha256(media)
    media.write_bytes(b"second")
    assert first_hash != file_sha256(media)
