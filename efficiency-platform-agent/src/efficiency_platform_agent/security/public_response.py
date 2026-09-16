"""对外回答发布前的最小治理。"""

from __future__ import annotations

import re

_ASSISTANT_BASE_LIMITATION_PATTERN = re.compile(
    r"(?:我|本助手|这个助手)(?:目前|暂时|并)?(?:不能|无法|不支持|不具备)"
    r"[^。！？\n]{0,48}(?:真正联网|联网|调用工具|使用工具|生成文件|创建文件|执行外部操作)"
)
_ASSISTANT_INTERNAL_DISCLOSURE_PATTERN = re.compile(
    r"(?:我的|本助手的)(?:系统提示|系统指令|隐藏思维|思维过程|推理过程)"
    r"|(?:系统提示|系统指令)\s*(?:要求我|让我)"
    r"|(?:隐藏思维|思维过程|推理过程)\s*(?:是|为)(?!模型|Agent|系统|Prompt|工具)[^。！？\n]"
)
_CREDENTIAL_LITERAL_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{16,}"
    r"|(?<![A-Za-z0-9_])Bearer\s+[A-Za-z0-9._~+/-]{16,}"
    r"|(?<![A-Za-z0-9_])(?:api[_-]?key|secret)\s*[:=]\s*['\"]?[A-Za-z0-9._~+/-]{12,}['\"]?",
    re.IGNORECASE,
)
_INTERNAL_EXCEPTION_PATTERN = re.compile(
    r"(?im)^\s*Traceback \(most recent call last\):"
    r"|[A-Za-z]:\\efficiency-platform(?:\\|$)"
    r'|^\s*File\s+"(?:[A-Za-z]:\\|/)[^"\n]+\.py",\s+line\s+\d+'
)
_SAFE_PRODUCT_RESPONSE = (
    "我可以协助公开资料整理、内容策划、品牌/IP、活动和渠道文案、运营复盘；"
    "需要时也能提供来源，方便你核验和继续推进。"
)
_BASE_SUBJECTS = ("我", "本助手", "这个助手")
_BASE_MODIFIERS = ("", "目前", "暂时", "并")
_BASE_NEGATIONS = ("不能", "无法", "不支持", "不具备")
_INTERNAL_DISCLOSURE_PREFIXES = (
    "我的系统提示",
    "我的系统指令",
    "我的隐藏思维",
    "我的思维过程",
    "我的推理过程",
    "本助手的系统提示",
    "本助手的系统指令",
    "本助手的隐藏思维",
    "本助手的思维过程",
    "本助手的推理过程",
    "系统提示要求我",
    "系统指令让我",
    "隐藏思维是",
    "隐藏思维为",
    "思维过程是",
    "思维过程为",
    "推理过程是",
    "推理过程为",
)
_SENSITIVE_STREAM_PREFIXES = (
    *_INTERNAL_DISCLOSURE_PREFIXES,
    "sk-",
    "Bearer ",
    "api_key",
    "api-key",
    "secret",
    "Traceback (most recent call last):",
    r"D:\efficiency-platform",
    'File "',
)
_CREDENTIAL_LITERAL_PREFIX_PATTERN = re.compile(
    r"(?i)(?:sk-[A-Za-z0-9_-]*"
    r"|Bearer\s+[A-Za-z0-9._~+/-]*"
    r"|(?:api[_-]?key|secret)\s*[:=]\s*['\"]?[A-Za-z0-9._~+/-]*)$"
)


class _PublicResponseStream:
    """在有限缓冲区中治理可能跨片段的敏感回答。"""

    def __init__(self, governor: PublicResponseGovernor) -> None:
        self.governor = governor
        self.pending = ""
        self.blocked = False

    def push(self, delta: str) -> str:
        """接收一个正文片段，只返回可安全公开的增量。"""
        if not isinstance(delta, str):
            raise TypeError("delta必须是字符串")
        if not delta or self.blocked:
            return ""
        combined = self.pending + delta
        if _contains_sensitive_response(combined):
            self.pending = ""
            self.blocked = True
            return _SAFE_PRODUCT_RESPONSE
        candidate_index = _sensitive_prefix_index(combined)
        if candidate_index is None:
            self.pending = ""
            return combined
        self.pending = combined[candidate_index:]
        return combined[:candidate_index]

    def finish(self) -> str:
        """在 Provider 正常结束时释放尚未构成敏感模式的缓冲正文。"""
        if self.blocked:
            return ""
        content = self.pending
        self.pending = ""
        return self.governor.govern(content)


class PublicResponseGovernor:
    """在发布前替换助手自身的底座否定或内部指令泄露。"""

    def govern(self, content: str) -> str:
        """保留正常技术讨论，仅替换明确的助手自身泄露。"""
        if not isinstance(content, str):
            raise TypeError("content必须是字符串")
        if _ASSISTANT_BASE_LIMITATION_PATTERN.search(content):
            return _SAFE_PRODUCT_RESPONSE
        if _ASSISTANT_INTERNAL_DISCLOSURE_PATTERN.search(content):
            return _SAFE_PRODUCT_RESPONSE
        if _CREDENTIAL_LITERAL_PATTERN.search(content):
            return _SAFE_PRODUCT_RESPONSE
        if _INTERNAL_EXCEPTION_PATTERN.search(content):
            return _SAFE_PRODUCT_RESPONSE
        return content

    def stream(self) -> _PublicResponseStream:
        """创建一个仅用于单次回答的跨片段治理器。"""
        return _PublicResponseStream(self)


def _contains_sensitive_response(content: str) -> bool:
    """判断缓冲正文是否已经构成需要替换的敏感回答。"""
    return bool(
        _ASSISTANT_BASE_LIMITATION_PATTERN.search(content)
        or _ASSISTANT_INTERNAL_DISCLOSURE_PATTERN.search(content)
        or _CREDENTIAL_LITERAL_PATTERN.search(content)
        or _INTERNAL_EXCEPTION_PATTERN.search(content)
    )


def _sensitive_prefix_index(content: str) -> int | None:
    """查找仍可能形成敏感模式的最早后缀，避免提前交付其前缀。"""
    for index, character in enumerate(content):
        if character in {
            "我",
            "本",
            "这",
            "系",
            "隐",
            "思",
            "推",
            "s",
            "S",
            "B",
            "b",
            "a",
            "A",
            "T",
            "t",
            "D",
            "d",
            "F",
            "f",
        } and _is_sensitive_prefix(content[index:]):
            return index
    return None


def _is_sensitive_prefix(content: str) -> bool:
    """判断有限后缀是否仍可能补全为已治理的敏感模式。"""
    if any(prefix.startswith(content) for prefix in _SENSITIVE_STREAM_PREFIXES):
        return True
    if _CREDENTIAL_LITERAL_PREFIX_PATTERN.fullmatch(content):
        return True
    for subject in _BASE_SUBJECTS:
        if subject.startswith(content):
            return True
        if not content.startswith(subject):
            continue
        remainder = content[len(subject) :]
        for modifier in _BASE_MODIFIERS:
            if modifier.startswith(remainder):
                return True
            if not remainder.startswith(modifier):
                continue
            after_modifier = remainder[len(modifier) :]
            for negation in _BASE_NEGATIONS:
                if negation.startswith(after_modifier):
                    return True
                if not after_modifier.startswith(negation):
                    continue
                tail = after_modifier[len(negation) :]
                if (
                    len(tail) <= 48
                    and not any(mark in tail for mark in "。！？\n")
                ):
                    return True
    return False


__all__ = ["PublicResponseGovernor"]
