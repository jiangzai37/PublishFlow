import json
from dataclasses import dataclass

import httpx

from app.config import get_settings


@dataclass
class GeneratedArticle:
    title: str
    body: str
    tags: list[str]


class OpenAICompatibleProvider:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def generate(
        self,
        topic: str,
        style: str = "清晰、自然、有信息量",
        length: int = 1200,
        with_headings: bool = True,
        with_tags: bool = True,
    ) -> GeneratedArticle:
        if not self.settings.model_api_key:
            raise ValueError("尚未配置模型 API Key，请在 .env 中设置 MODEL_API_KEY。")
        headings = "使用少量 Markdown 二级标题组织段落" if with_headings else "不要使用标题"
        tags = "并生成 3 个话题标签" if with_tags else "不要生成标签"
        prompt = (
            f"你是一位中文内容编辑。请围绕主题「{topic}」创作一篇原创文章。"
            f"风格：{style}。目标长度约 {length} 字。{headings}，{tags}。"
            "避免虚构事实、夸张承诺与广告化表达。只返回 JSON，格式为 "
            '{"title":"标题","body":"Markdown 正文","tags":["标签"]}。'
        )
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{self.settings.model_base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {self.settings.model_api_key}"},
                json={
                    "model": self.settings.model_name,
                    "temperature": 0.7,
                    "messages": [
                        {
                            "role": "system",
                            "content": "你是严谨、克制的中文内容编辑。只输出合法 JSON。",
                        },
                        {"role": "user", "content": prompt},
                    ],
                },
            )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0]
        article = json.loads(content)
        return GeneratedArticle(
            title=str(article.get("title", topic))[:300],
            body=str(article.get("body", "")),
            tags=[str(tag).lstrip("#")[:30] for tag in article.get("tags", [])[:5]],
        )

    async def adapt(self, title: str, body: str, target_platform: str) -> GeneratedArticle:
        if not self.settings.model_api_key:
            raise ValueError("尚未配置模型 API Key，无法进行平台适配改写。")
        platform = "CSDN 技术博客" if target_platform == "csdn" else "知乎知识社区"
        prompt = (
            f"请将以下原创内容适配为{platform}的发布版本。保留事实、观点与素材引用，"
            "不虚构经历、数据或来源，不使用夸张承诺和广告化表达。"
            "CSDN 使用清晰 Markdown 技术结构；知乎使用自然、有逻辑的问答式表达。"
            '只返回合法 JSON，格式为 {"title":"标题","body":"Markdown 正文","tags":["标签"]}。'
            f"原标题：{title}\n\n原文：\n{body}"
        )
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{self.settings.model_base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {self.settings.model_api_key}"},
                json={
                    "model": self.settings.model_name,
                    "temperature": 0.5,
                    "messages": [
                        {
                            "role": "system",
                            "content": "你是严谨、克制的中文内容编辑。只输出合法 JSON。",
                        },
                        {"role": "user", "content": prompt},
                    ],
                },
            )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0]
        article = json.loads(content)
        return GeneratedArticle(
            title=str(article.get("title", title))[:300],
            body=str(article.get("body", "")),
            tags=[str(tag).lstrip("#")[:30] for tag in article.get("tags", [])[:5]],
        )
