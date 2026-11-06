"""System prompt sections: identity before data, and no empty headings."""

from __future__ import annotations

from soapbot.ai.persona import Persona


def _persona() -> Persona:
    return Persona(
        id="demo",
        name="Demo",
        system_prompt="你是群里的助手。",
        style="简短",
        max_reply_chars=200,
        banned_words=["脏话"],
    )


def test_identity_comes_before_any_recalled_text() -> None:
    """A flat prompt lets an attacker's sentence read like an operator rule."""
    text = _persona().build_system_prompt("【会话摘要】他们昨天在聊部署。")

    assert text.index("【核心设定】") < text.index("【外部内容】")


def test_core_section_keeps_style_length_and_banned_words() -> None:
    text = _persona().build_system_prompt("")

    assert "你是群里的助手。" in text
    assert "简短" in text
    assert "200" in text
    assert "脏话" in text


def test_empty_sections_are_omitted() -> None:
    text = _persona().build_system_prompt("")

    assert "【长期记忆】" not in text
    assert "【近期事件】" not in text
    assert "【当前任务】" not in text
    assert "【工具说明】" not in text
    assert "【外部内容】" not in text


def test_optional_sections_render_in_a_fixed_order() -> None:
    text = _persona().build_system_prompt(
        "检索到的片段",
        memory_note="小明喜欢猫。",
        timeline_note="刚才调用了搜索。",
        task_note="回答当前问题。",
        tools_note="search(query)",
    )

    order = [
        "【核心设定】",
        "【长期记忆】",
        "【近期事件】",
        "【当前任务】",
        "【工具说明】",
        "【外部内容】",
    ]
    positions = [text.index(heading) for heading in order]
    assert positions == sorted(positions)


def test_a_persona_without_a_body_still_orders_data_sections() -> None:
    """No prose does not mean no core section: max_reply_chars is still an instruction."""
    bare = Persona(id="bare", name="Bare")
    text = bare.build_system_prompt("检索片段", memory_note="一条记忆")

    assert "【长期记忆】" in text
    assert "【外部内容】" in text
    assert text.index("【长期记忆】") < text.index("【外部内容】")
