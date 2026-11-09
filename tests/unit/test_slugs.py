"""Slug rule (spec/data-model.md §Phase 11e → Slug rule)."""

import re

import pytest

from src.workshop0.services import slugs


@pytest.mark.parametrize(
    ("title", "city", "expected"),
    [
        ("GenAI Workshop", "Bengaluru", "genai-workshop-bengaluru"),
        ("Zürich  Data — Bootcamp!", None, "zurich-data-bootcamp"),
        ("São Paulo", "São Paulo", "sao-paulo-sao-paulo"),
        ("कार्यशाला प्रशिक्षण", None, "opportunity"),
        ("कार्यशाला", "Pune", "pune"),
        ("---", "", "opportunity"),
    ],
)
def test_slug_base(title, city, expected):
    assert slugs.slug_base(title, city) == expected


def test_long_title_is_cut_on_a_word_boundary():
    title = " ".join(["workshop"] * 18)[:160]
    assert len(title) == 160
    base = slugs.slug_base(title, "Bengaluru")
    assert len(base) <= 60
    assert not base.endswith("-") and not base.startswith("-")
    assert all(word == "workshop" for word in base.split("-"))  # never cut mid-word


def test_single_long_word_is_hard_cut_at_60():
    assert slugs.slug_base("x" * 100, None) == "x" * 60


def test_suffix_is_4_lower_hex():
    for _ in range(50):
        assert re.fullmatch(r"[0-9a-f]{4}", slugs.new_suffix())


def test_unique_slug_without_collision():
    slug = slugs.make_unique_slug("genai-workshop", lambda s: False)
    assert re.fullmatch(r"genai-workshop-[0-9a-f]{4}", slug)


def test_five_collisions_switch_to_six_hex(monkeypatch):
    monkeypatch.setattr(slugs, "new_suffix", lambda nbytes=2: "a" * (2 * nbytes))
    seen: list[str] = []

    def exists(candidate: str) -> bool:
        seen.append(candidate)
        return candidate == "base-aaaa"  # every 4-hex draw collides

    slug = slugs.make_unique_slug("base", exists)
    assert slug == "base-aaaaaa"
    assert seen.count("base-aaaa") == 5


def test_generated_slugs_are_never_all_digits():
    for title, city in [("2026", "1"), ("123", None), ("", None), ("42 42", "7")]:
        slug = slugs.make_unique_slug(slugs.slug_base(title, city), lambda s: False)
        assert not re.fullmatch(r"\d+", slug), slug
        assert "-" in slug
