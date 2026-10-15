"""根据已校验排名引用生成事实闭合的平台成稿草案。"""

from __future__ import annotations

import json
from typing import Any

from efficiency_platform_agent.core.model import ModelExecutionResult
from efficiency_platform_agent.core.run import (
    ProviderMessage,
    ProviderResult,
    ProviderUsage,
)
from efficiency_platform_agent.core.runtime import UsageSnapshot


class ReferencedContentModelRuntime:
    """有类型化跨轮引用时确定性成稿；其他请求仍交给真实模型。"""

    def __init__(self, delegate: Any) -> None:
        self.delegate = delegate

    async def complete(self, demand, request, **kwargs) -> ModelExecutionResult:
        raw = _request_payload(request.messages)
        draft = _build_draft(raw) if raw is not None else None
        if draft is None:
            return await self.delegate.complete(demand, request, **kwargs)
        return ModelExecutionResult(
            ProviderResult(
                "provider-result/1",
                ProviderMessage("assistant", json.dumps(draft, ensure_ascii=False)),
                ProviderUsage(0, 0, 0, 0, 0),
            ),
            (),
            UsageSnapshot(),
            False,
        )


def _request_payload(messages: tuple[ProviderMessage, ...]) -> dict[str, Any] | None:
    content = messages[-1].content
    if not isinstance(content, str):
        return None
    try:
        value = json.loads(content)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _build_draft(raw: dict[str, Any]) -> dict[str, Any] | None:
    inputs = raw.get("input_deliverables")
    if not isinstance(inputs, list):
        return None
    items = [
        value["item"]
        for value in inputs
        if isinstance(value, dict) and isinstance(value.get("item"), dict)
    ]
    if not items:
        return None
    platform = raw.get("platform")
    if platform == "wechat_official_account":
        title = "本周 AI 热点观察：从真实动态看产品与技术的新信号"
        body = _wechat_article(title, items)
        hashtags: list[str] = []
        notes = ["公众号 Markdown 标准排版", "事实范围限于所附来源摘要"]
    elif platform == "xiaohongshu":
        title = f"AI 热点速递｜{str(items[0].get('title', '本周新动态'))[:80]}"
        body = _xiaohongshu_post(title, items[0])
        hashtags = ["#AI行业动态", "#人工智能", "#科技观察"]
        notes = ["小红书分段排版", "保留已核验信息边界"]
    else:
        return None
    return {
        "contract_version": "deliverable/2",
        "deliverable_id": raw["deliverable_id"],
        "deliverable_kind": "platform_content",
        "platform": platform,
        "title": title,
        "lead": "已根据上一轮有效热点条目完成平台化整理，正文不扩展未核验事实。",
        "citations": [],
        "copy_text": "",
        "warnings": [],
        "content": {
            "kind": "platform_content",
            "body_markdown": body,
            "hashtags": hashtags,
            "format_notes": notes,
        },
    }


def _wechat_article(title: str, items: list[dict[str, Any]]) -> str:
    sections = [
        f"# {title}",
        (
            "AI 行业的信息密度仍在持续上升。真正值得进入周更的，不只是一个醒目的标题，"
            "而是已经能够回到公开来源、核对时间与原始表述的有效动态。下面按本次已核验"
            f"的 {len(items)} 条信息展开，帮助产品、运营与内容团队快速建立本周观察坐标。"
        ),
    ]
    for index, item in enumerate(items, start=1):
        item_title = str(item.get("title") or f"热点 {index}").strip()
        summary = str(item.get("summary") or item_title).strip()
        why = str(item.get("why_it_matters") or "值得继续跟踪后续公开进展。").strip()
        sections.extend(
            (
                f"## {index:02d}｜{item_title}",
                f"**已核验信息**\n\n{summary}",
                f"**为什么值得关注**\n\n{why}",
                (
                    "**内容观察**\n\n这条动态适合继续沿着“发生了什么、影响哪些使用场景、"
                    "后续还有什么公开信号”三个问题跟踪。现阶段应以所附来源为事实边界，"
                    "不把尚未出现的数字、结论或产品承诺写进传播内容。"
                ),
            )
        )
    sections.extend(
        (
            "## 本周内容团队可以怎么用",
            (
                "第一，优先保留能够回到原始页面的信息，把标题、摘要和判断分开呈现；"
                "第二，把同一热点拆成产品视角、技术视角和用户视角，避免只复述新闻；"
                "第三，对仍在变化中的内容保留时间标记，后续更新时重新核验，而不是沿用旧结论。"
            ),
            "## 结语",
            (
                "热点的价值不在于数量越多越好，而在于每一条都能说明来源、信息边界和继续观察的方向。"
                "这份周更只使用本轮已经核验的有效条目；未达到十条时保持真实数量，不用未经核实的内容补位。"
            ),
        )
    )
    return "\n\n".join(sections)


def _xiaohongshu_post(title: str, item: dict[str, Any]) -> str:
    summary = str(item.get("summary") or item.get("title") or "").strip()
    why = str(item.get("why_it_matters") or "值得继续关注后续公开进展。").strip()
    return "\n\n".join(
        (
            f"# {title}",
            f"📌 已核验信息\n{summary}",
            f"💡 为什么值得关注\n{why}",
            (
                "🔎 我的观察\n这条信息适合从产品变化、真实使用场景和后续公开进展三个角度继续跟踪。"
                "当前只整理已核验内容，不把猜测写成事实。"
            ),
            "你最想继续了解它的哪个方向？欢迎留言聊聊。",
        )
    )


__all__ = ["ReferencedContentModelRuntime"]
