"""Planner AI – generates road trip itineraries based on user constraints."""

from __future__ import annotations

import os

import llm_client

SYSTEM_PROMPT = """\
あなたはロードトリップの旅程を計画する専門AIプランナーです。

## あなたの役割
ユーザーが提供する「確定条件」と「希望条件」に基づいて、魅力的で実現可能なロードトリッププランを作成してください。

## 出力ルール
1. プランはMarkdown形式で出力してください。ユーザーはこのMarkdownをファイルとして閲覧します。
2. 日ごとにセクション（## Day 1, ## Day 2, ...）を分け、各日の移動ルート・立ち寄りスポット・宿泊先を明記してください。
3. 各スポットには以下を含めてください:
   - スポット名（クリック可能なGoogle Mapsリンク付き。下記フォーマット参照）
   - 簡単な説明（1-2文）
   - おすすめの滞在時間
   - 前のスポットからのおおよその移動時間
4. ユーザーの確定条件に記載された指示には必ず従ってください。
5. **Google Mapsリンクのフォーマット（厳守）**: スポットごとに以下のMarkdownリンク形式で出力してください。スポット名はURLエンコードしてください:
   `[📍 スポット名](https://www.google.com/maps/search/スポット名)`
   例: `[📍 河口湖](https://www.google.com/maps/search/%E6%B2%B3%E5%8F%A3%E6%B9%96)`
6. 全体のスケジュールに無理がないよう、移動時間と滞在時間のバランスを考慮してください。
7. プランの先頭にタイトルを `#` 見出しで付けてください（例: `# 🏔️ 信州アルプス＆温泉満喫の旅`）。

## 実在性チェック（重要）
提案するすべての場所（国立公園、トレイル、レストラン、店舗、宿泊施設など）が **確実に実在するか、Google検索機能を用いて必ず確認** してください。実在しない架空の場所は絶対に含めないでください。

## フィードバックへの対応
「フィードバック履歴」セクションがある場合、過去のフィードバックを注意深く読み、同じ問題を繰り返さないようにしてください。

## レビュー不合格への対応
「レビュー指摘事項」が提供された場合、指摘された全ての問題を修正してプランを再生成してください。
"""


REFINE_SYSTEM_PROMPT = """\
あなたはロードトリップの旅程を修正する専門AIプランナーです。

## あなたの役割
すでに作成されたプランに対して、「詳細チェック（実在性・設備等）」で不合格となった箇所の指摘事項を受け取ります。
指摘事項を修正するために、**問題のある箇所（特定のスポットや宿泊先など）のみを別の適切な場所に変更**し、プラン全体を出力し直してください。

## 修正のルール
1. 指摘されていない日やスポットのスケジュールは、**可能な限り元のプランのまま維持**してください。全体を0から作り直さないでください。
2. 修正した箇所は、移動時間や滞在時間の辻褄が合うように前後のスケジュールも微調整してください。
3. すべての確定条件と、前回までのフィードバック履歴（もしあれば）を引き続き遵守してください。
4. Markdown形式で出力し、Google Mapsリンクのフォーマットも元プランと同様に厳守してください。
5. 提案する新しい場所が実在するかどうかに細心の注意を払ってください。
"""

def generate_plan(
    trip_input: str,
    review_issues: list[str] | None = None,
    cache_name: str | None = None,
) -> str:
    """Generate a road trip plan from scratch.

    Args:
        trip_input: The full content of trip_input.md.
        review_issues: Optional list of issues from a previous OVERALL review rejection.
        cache_name: Optional explicitly created Gemini Cache name for reusing trip_input context.

    Returns:
        The generated plan in Markdown format.
    """
    user_prompt = f"以下のロードトリップ計画の入力に基づいて、旅程プランを作成してください。\n\n{trip_input}"

    if review_issues:
        issues_text = "\n".join(f"- {issue}" for issue in review_issues)
        user_prompt += (
            f"\n\n## レビュー指摘事項（前回の全体プランが不合格になった理由）\n\n"
            f"以下の問題を全て修正してプランを再生成してください:\n{issues_text}"
        )

    provider = os.environ.get("PLANNER_PROVIDER")
    model = os.environ.get("PLANNER_MODEL")
    return llm_client.generate(SYSTEM_PROMPT, user_prompt, use_search=False, provider=provider, model=model, cache_name=cache_name)


def refine_plan(
    plan: str,
    trip_input: str,
    review_issues: list[str],
    cache_name: str | None = None,
) -> str:
    """Refine an existing plan based on detailed review issues.

    Args:
        plan: The current plan that has some issues.
        trip_input: The full content of trip_input.md (for reference).
        review_issues: List of issues found in the detailed review.
        cache_name: Optional explicitly created Gemini Cache name for reusing trip_input context.

    Returns:
        The refined plan in Markdown format.
    """
    issues_text = "\n".join(f"- {issue}" for issue in review_issues)
    user_prompt = (
        "以下の現在のプランには、いくつか実在性や設備条件に関する問題が指摘されています。\n"
        "指摘事項を解決するように該当箇所のみを修正し、新しいプランのMarkdownを出力してください。\n\n"
        "## 指摘事項\n\n"
        f"{issues_text}\n\n"
        "## 確定条件（参考）\n\n"
        f"{trip_input}\n\n"
        "## 現在のプラン\n\n"
        f"{plan}"
    )

    provider = os.environ.get("PLANNER_PROVIDER")
    model = os.environ.get("PLANNER_MODEL")
    return llm_client.generate(REFINE_SYSTEM_PROMPT, user_prompt, use_search=False, provider=provider, model=model, cache_name=cache_name)

