import html
import json
import re

import markdown
import nh3

from app.core.typesetting.presets import get_preset

ALLOWED_TAGS = {
    "p",
    "br",
    "h1",
    "h2",
    "h3",
    "h4",
    "strong",
    "em",
    "ul",
    "ol",
    "li",
    "blockquote",
    "img",
    "a",
    "pre",
    "code",
    "hr",
    "figure",
    "figcaption",
    "span",
}


def render_article(
    title: str,
    body: str,
    preset_id: str,
    cover_url: str | None = None,
    preset: dict | None = None,
) -> str:
    preset = preset or get_preset(preset_id)
    style = json.loads(preset["style_json"])
    body_html = markdown.markdown(body, extensions=["extra", "sane_lists"])
    body_html = nh3.clean(
        body_html,
        tags=ALLOWED_TAGS,
        attributes={"img": {"src", "alt"}, "a": {"href", "title"}, "span": {"class"}},
        url_schemes={"http", "https", "mailto"},
    )
    accent = style.get("accent", "#a44732")
    heading_decoration = (
        "border-left:4px solid currentColor;padding-left:14px;"
        if style["headingStyle"] == "left-border"
        else ""
    )
    cover_html = (
        f'<figure><img src="{html.escape(cover_url, quote=True)}" alt="文章封面">'
        "<figcaption>封面图</figcaption></figure>"
        if cover_url and style.get("firstImageRule", "cover") != "none"
        else ""
    )
    tail = style.get("tailText", "")
    quote_style = style.get("quoteStyle", "paper")
    quote_background = (
        "transparent"
        if quote_style == "none"
        else ("#f2eee6" if quote_style == "paper" else "transparent")
    )
    heading_class = style.get("headingStyle", "left-border")
    return f"""<article class="rendered-article preset-{heading_class}" style="font-family:{html.escape(style["fontFamily"], quote=True)};font-size:{style["fontSize"]}px;line-height:{style["lineHeight"]};color:#2d2924;">
<h1 style="font-size:2em;line-height:1.35;margin:0 0 28px;letter-spacing:-.03em;color:#211e1a;">{html.escape(title)}</h1>
{cover_html}
<div class="article-body" style="color:{accent};">{body_html}</div>
{f'<footer style="margin-top:36px;padding-top:20px;border-top:1px solid #ddd5c8;color:#837a6c;font-size:13px;">{html.escape(tail)}</footer>' if tail else ""}
</article>
<style>
.rendered-article p{{margin:0 0 {style["paragraphSpacing"]}px;}}
.rendered-article h2,.rendered-article h3{{color:#211e1a;margin:34px 0 16px;{heading_decoration}}}
.rendered-article.preset-numbered h2,.rendered-article.preset-numbered h3{{counter-increment:section;}}
.rendered-article.preset-numbered h2::before,.rendered-article.preset-numbered h3::before{{content:counter(section,decimal-leading-zero) '  ';color:{accent};font-family:Georgia,serif;font-weight:400;}}
.rendered-article{{counter-reset:section;}}
.rendered-article blockquote{{margin:24px 0;padding:14px 20px;border-left:3px solid {accent};background:{quote_background};color:#655e54;}}
.rendered-article img{{max-width:100%;height:auto;border-radius:4px;}}
.rendered-article figcaption{{text-align:center;color:#8a8175;font-size:12px;margin-top:8px;}}
.rendered-article pre{{background:#f1eee8;padding:16px;overflow:auto;}}
.rendered-article a{{color:{accent};}}
</style>"""


def plain_text_from_html(content_html: str) -> str:
    text = re.sub(
        r"<(style|script)\b[^>]*>.*?</\1>", "", content_html, flags=re.DOTALL | re.IGNORECASE
    )
    text = re.sub(r"</(p|h[1-6]|li|blockquote|figcaption)>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\n{3,}", "\n\n", html.unescape(text)).strip()
