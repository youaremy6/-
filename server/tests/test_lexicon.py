"""Offline lexicon behaviour for the universal Gansu question word."""

from __future__ import annotations

from app.services import lexicon


def test_universal_question_word_to_mandarin():
    normalized, uncertain = lexicon.to_mandarin("你组撒呢？")
    assert normalized == "你干什么呢？"
    assert "组撒" in uncertain


def test_universal_question_word_variants():
    assert lexicon.to_mandarin("做撒？")[0] == "干什么？"
    assert lexicon.to_mandarin("组啥？")[0] == "干什么？"


def test_universal_question_word_to_lanzhou():
    assert lexicon.to_lanzhou("你在做什么？")[0] == "你在组撒？"
    assert lexicon.to_lanzhou("干啥？")[0] == "组撒？"
    assert lexicon.to_lanzhou("你在干什么？")[0] == "你在组撒？"


def test_daily_words_to_mandarin():
    assert lexicon.to_mandarin("没麻达")[0] == "没问题"
    assert lexicon.to_mandarin("攒劲")[0] == "厉害"
    assert lexicon.to_mandarin("干散")[0] == "利落"
    assert lexicon.to_mandarin("瓜怂")[0] == "傻子"
    assert lexicon.to_mandarin("日厌")[0] == "讨厌"
    assert lexicon.to_mandarin("坏怂")[0] == "坏蛋"


def test_daily_words_to_lanzhou():
    assert lexicon.to_lanzhou("没问题")[0] == "没麻达"
    assert lexicon.to_lanzhou("厉害")[0] == "攒劲"
    assert lexicon.to_lanzhou("做事利落")[0] == "做事干散"
    assert lexicon.to_lanzhou("傻子")[0] == "瓜怂"
    assert lexicon.to_lanzhou("讨厌")[0] == "日厌"
    assert lexicon.to_lanzhou("坏蛋")[0] == "坏怂"
