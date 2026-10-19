#!/usr/bin/env python3
"""見出しの切り方。括弧の外の文末まで取り、閉じない括弧を出さない。"""

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rebuild_index as rebuild


PAIRS = {
    "（": "）", "(": ")", "「": "」", "『": "』", "【": "】",
    "[": "]", "［": "］", "〈": "〉", "《": "》", "“": "”", "‘": "’",
}


def unclosed(text: str) -> str:
    stack = []
    close = {v: k for k, v in PAIRS.items()}
    for ch in text:
        if ch in PAIRS:
            stack.append(ch)
        elif ch in close and stack and stack[-1] == close[ch]:
            stack.pop()
    if text.count('"') % 2 == 1:
        stack.append('"')
    return "".join(stack)


class HeadlineTests(unittest.TestCase):
    def test_ja_period_inside_parens_is_not_the_end(self):
        text = (
            "METRの評価者6名に、社内と同等のアクセスと公表する権利を与えた"
            "（公式、10/15。脚注は10/16に更新）。METRから6名を受け入れた。"
        )
        head = rebuild.to_headline(text, "ja")
        self.assertEqual(
            head,
            "METRの評価者6名に、社内と同等のアクセスと公表する権利を与えた"
            "（公式、10/15。脚注は10/16に更新）",
        )
        self.assertNotIn("…", head)
        self.assertEqual(unclosed(head), "")

    def test_ja_keeps_the_rest_of_the_sentence_past_sixty(self):
        text = (
            "NTTデータグループが、大阪にAnthropic向けのデータセンターを新設する方向で"
            "最終調整していると、日経と朝日が報じた（10/13）。その後の調整が続く。"
        )
        head = rebuild.to_headline(text, "ja")
        self.assertEqual(
            head,
            "NTTデータグループが、大阪にAnthropic向けのデータセンターを新設する方向で"
            "最終調整していると、日経と朝日が報じた（10/13）",
        )
        self.assertGreater(len(head), rebuild.HEADLINE_LEN)
        self.assertFalse(head.endswith("…"))
        self.assertEqual(unclosed(head), "")

    def test_en_keeps_parenthetical_past_the_limit(self):
        text = (
            "Gave six METR evaluators access equal to internal staff and the right to publish "
            "(official, Oct 15; footnote updated Oct 16). The program starts next month."
        )
        head = rebuild.to_headline(text, "en")
        self.assertEqual(
            head,
            "Gave six METR evaluators access equal to internal staff and the right to publish "
            "(official, Oct 15; footnote updated Oct 16)",
        )
        self.assertGreater(len(head), rebuild.HEADLINE_LEN_EN)
        self.assertFalse(head.endswith("…"))
        self.assertEqual(unclosed(head), "")

    def test_en_does_not_stop_at_a_period_inside_parens(self):
        text = "Noted the change (updated Oct. 15). Another sentence follows."
        head = rebuild.to_headline(text, "en")
        self.assertEqual(head, "Noted the change (updated Oct. 15)")
        self.assertEqual(unclosed(head), "")

    def test_en_abbreviation_and_decimal_are_not_the_end(self):
        self.assertEqual(
            rebuild.to_headline("U.S. officials agreed today. More later.", "en"),
            "U.S. officials agreed today",
        )
        self.assertEqual(
            rebuild.to_headline("Version 1.5 ships today. More later.", "en"),
            "Version 1.5 ships today",
        )

    def test_closing_quote_after_the_period_stays(self):
        text = (
            'Announced at a White House summit on Oct 8 that it will commit $150 million '
            'over 3 years to the US government science project "Genesis Mission." '
            "It will provide Claude."
        )
        head = rebuild.to_headline(text, "en")
        self.assertTrue(head.endswith('"Genesis Mission"'))
        self.assertEqual(unclosed(head), "")
        self.assertNotIn("…", head)

    def test_short_headlines_stay_whole(self):
        self.assertEqual(rebuild.to_headline("短い見出しです。続き。", "ja"), "短い見出しです")
        self.assertEqual(rebuild.to_headline("A short headline. More.", "en"), "A short headline")

    def test_clip_without_a_sentence_end_stays_outside_brackets(self):
        # 60字の直前で括弧が開く。括弧の中では切らない。
        body = "あ" * 50 + "（この括弧は長い説明が続いてまだ閉じない"
        self.assertGreater(len(body), rebuild.HEADLINE_LEN)
        head = rebuild.to_headline(body, "ja")
        self.assertTrue(head.endswith("…"))
        self.assertEqual(unclosed(head), "")
        self.assertNotIn("（", head)

        words = " ".join(["word"] * 40) + " (a parenthetical that runs on without a close"
        self.assertGreater(len(words), rebuild.HEADLINE_LEN_EN)
        en = rebuild.to_headline(words, "en")
        self.assertTrue(en.endswith("…"))
        self.assertEqual(unclosed(en), "")
        self.assertNotIn("(", en)

    def test_published_headlines_have_no_open_brackets(self):
        for lang, posts in (
            ("ja", rebuild.collect_posts()),
            ("en", rebuild.collect_posts(rebuild.EN_POSTS_DIR, lang="en")),
        ):
            for post in posts:
                for item in post["headlines"]:
                    text = item["text"]
                    self.assertEqual(
                        unclosed(text),
                        "",
                        f"{lang} {post['date']}: {text}",
                    )


if __name__ == "__main__":
    unittest.main()
