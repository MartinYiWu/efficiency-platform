from efficiency_platform_agent.capabilities.quality.deliverable_assembler import (
    DeliverableAssembler,
)


def test_xiaohongshu_body_hashtags_are_promoted_to_structured_field() -> None:
    result = DeliverableAssembler().assemble(
        (
            {
                "platform": "xiaohongshu",
                "title": "程序员降噪耳机",
                "body": "专注写代码，告别环境噪声。\n#程序员 #降噪耳机 #专注力",
                "hashtags": [],
            },
        )
    )

    deliverable = result.deliverables[0]
    assert deliverable.hashtags == ["#程序员", "#降噪耳机", "#专注力"]
    assert "PLATFORM_HASHTAGS_MISSING" not in deliverable.warnings
