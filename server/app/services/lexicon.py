"""Conservative Lanzhou <-> Mandarin word lists used by the offline provider.

These are *draft* lexical hints, not an authoritative dictionary.  Every entry
that is not backed by the reviewed phrase pack is reported as an uncertain
word so the UI can ask the user to confirm.  The live provider uses the same
list only as LLM context, never as a silent replacement rule.
"""

from __future__ import annotations

# Lanzhou -> Mandarin.  Order matters: longer phrases first.
LANZHOU_TO_MANDARIN: list[tuple[str, str]] = [
    ("夜来个", "昨天"),
    ("谝闲传", "聊天"),
    ("没麻达", "没问题"),
    ("么麻达", "没问题"),
    ("干散", "利落"),
    ("瓜怂", "傻子"),
    ("日厌", "讨厌"),
    ("日眼", "讨厌"),
    ("坏怂", "坏蛋"),
    ("组撒", "干什么"),
    ("做撒", "干什么"),
    ("组啥", "干什么"),
    ("阿达", "哪里"),
    ("哪达", "哪里"),
    ("这达", "这里"),
    ("那达", "那里"),
    ("脑壳", "头"),
    ("尕", "小"),
    ("一挂", "一下"),
    ("一哈", "一下"),
    ("咋走", "怎么走"),
    ("咋", "怎么"),
    ("难活", "难受"),
    ("攒劲", "厉害"),
    ("能行", "可以"),
    ("啥", "什么"),
    ("大夫", "医生"),
    ("哩", ""),
]

# Mandarin -> Lanzhou, applied only on exact token boundaries where possible.
MANDARIN_TO_LANZHOU: list[tuple[str, str]] = [
    ("聊天", "谝闲传"),
    ("没问题", "没麻达"),
    ("利落", "干散"),
    ("傻子", "瓜怂"),
    ("讨厌", "日厌"),
    ("坏蛋", "坏怂"),
    ("干什么", "组撒"),
    ("做什么", "组撒"),
    ("干啥", "组撒"),
    ("怎么走", "咋走"),
    ("怎么", "咋"),
    ("医生", "大夫"),
    ("哪里", "阿达"),
    ("这儿", "这达"),
    ("昨天", "夜来个"),
    ("一下", "一挂"),
    ("难受", "难活"),
    ("厉害", "攒劲"),
    ("可以", "能行"),
    ("什么", "啥"),
    ("头", "脑壳"),
    ("小", "尕"),
]


def to_mandarin(text: str) -> tuple[str, list[str]]:
    """Rule-based normalization used only when no LLM is configured."""
    out = text
    uncertain: list[str] = []
    for src, dst in LANZHOU_TO_MANDARIN:
        if src in out:
            out = out.replace(src, dst)
            if src not in uncertain and src not in {"哩"}:
                uncertain.append(src)
    # Sentence-final 不 -> 吗 in yes/no questions ("能吃不" -> "能吃吗").
    if out.endswith("不") and len(out) > 1:
        out = out[:-1] + "吗"
        uncertain.append("不")
    return out, uncertain


def to_lanzhou(text: str) -> tuple[str, list[str]]:
    out = text
    uncertain: list[str] = []
    for src, dst in MANDARIN_TO_LANZHOU:
        if src in out:
            out = out.replace(src, dst, 1)
            if src not in uncertain:
                uncertain.append(src)
    return out, uncertain
