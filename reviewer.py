"""Reviewer AI – validates that generated plans meet all hard constraints."""

from __future__ import annotations

import json
import os
import re

import llm_client

SYSTEM_PROMPT_OVERALL = """\
あなたはロードトリッププランの「必要最低限のチェックのみを行う寛容なレビュワーAI（全体チェック担当）」です。
ハルシネーションや明らかな構造的欠陥を防ぐことだけが目的です。

## あなたの役割
提案されたプランの**骨格部分**のみをチェックし、物理的に不可能などの致命的な欠陥がない限りは**必ず合格（approved: true）**としてください。
検索機能は使用しません。

## チェック項目（これ以外はチェックしないでください）
1. **日程**: プランの日数が確定条件の日程（例: 4泊5日）と一致しているか。
2. **出発地/到着地**: プランの最初の出発地と最後の到着地が確定条件の通りか。
3. **物理的実現可能性**: 1日の移動距離が「物理的に不可能」レベル（例: 1日に1000km以上など）でないか。1日400km程度までの移動は完全に許容してください。

## 重要な注意（絶対厳守）
- **減点方式ではなく、加点方式・寛容な態度でレビューしてください。**
- **「希望条件」や「フィードバック履歴」は一切チェックしないでください。これらを理由にした不合格は禁止です。**
- 「移動の無駄がある」「観光の楽しみが少ない」「時間が不明確」「もっと早く出発すべき」などの**主観的な理由や、提案内容の質を理由に不合格にしないでください**。
- キャンプ場に泊まる義務はありません。キャンプ場以外の宿泊（ホテルなど）が含まれていても問題ありません。
- 細かい設備（シャワーの有無など）や実在性は後続のプロセスでチェックするため、ここでは一切言及せず合格としてください。
- 疑わしい場合は必ず「合格（approved: true）」としてください。

## 出力形式
必ず以下のJSON形式のみで回答してください。JSON以外のテキストは含めないでください。

```json
{
  "approved": true または false,
  "issues": ["問題点1", "問題点2"]
}
```

- `approved` が `true` の場合、`issues` は空配列 `[]` にしてください。
- `approved` が `false` の場合、`issues` に具体的な問題点を全て列挙してください。
"""

SYSTEM_PROMPT_DETAILED = """\
あなたはロードトリッププランの厳格なレビュワーAI（詳細チェック担当）です。

## あなたの役割
ユーザーが定義した「確定条件」に対して、提案されたプランの**詳細なスポット情報**が条件を満たしているかを厳密にチェックしてください。
また、プランに架空の場所が含まれていないか、Google検索を用いて必ず検証してください。

## チェック項目
1. **指示の遵守**: 確定条件に記載された全ての指示（例: 特定の設備の有無、Google Mapsリンクの付与）に従っているか。
2. **実在性の確認（重要）**: 提案されたすべての場所（国立公園、トレイル、レストラン、店舗、宿泊施設など）が実際に存在するか。Google検索を用いて必ず裏付けを取ってください。実在が疑わしい場所や、条件を満たす設備（例: 電源、シャワー）がない場所が含まれる場合は不合格としてください。

## 重要な注意
- 「希望条件」は推奨事項であり、満たしていなくても不合格にしないでください。
- 「確定条件」と「実在性の確認」のみを基準に合否を判定してください。

## 出力形式
必ず以下のJSON形式のみで回答してください。JSON以外のテキストは含めないでください。

```json
{
  "approved": true または false,
  "issues": ["問題点1", "問題点2"]
}
```

- `approved` が `true` の場合、`issues` は空配列 `[]` にしてください。
- `approved` が `false` の場合、`issues` に具体的な問題点を全て列挙してください。（例: 「Day 2の〇〇キャンプ場にはシャワー設備がありません。」）
"""


class ReviewResult:
    """Holds the result of a plan review."""

    def __init__(self, approved: bool, issues: list[str]):
        self.approved = approved
        self.issues = issues

    def __repr__(self) -> str:
        status = "✅ 合格" if self.approved else "❌ 不合格"
        return f"ReviewResult({status}, issues={self.issues})"


def _parse_review_response(response: str) -> ReviewResult:
    """Parse the JSON response from the reviewer.

    Attempts to extract JSON from the response text, handling cases where
    the model wraps it in markdown code blocks.

    Args:
        response: The raw text response from the model.

    Returns:
        A ReviewResult object.
    """
    # Try to extract JSON from code blocks first
    json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", response, re.DOTALL)
    if json_match:
        json_str = json_match.group(1).strip()
    else:
        # Try the raw response
        json_str = response.strip()

    try:
        data = json.loads(json_str)
        return ReviewResult(
            approved=bool(data.get("approved", False)),
            issues=list(data.get("issues", [])),
        )
    except (json.JSONDecodeError, AttributeError):
        # If parsing fails, treat it as a failure with the raw response as the issue
        return ReviewResult(
            approved=False,
            issues=[f"レビュー結果の解析に失敗しました。生のレスポンス: {response[:500]}"],
        )


def review_overall(trip_input: str, plan: str) -> ReviewResult:
    """Review the overall structure of a generated plan against the trip constraints.

    Args:
        trip_input: The full content of trip_input.md (constraints).
        plan: The generated plan to review.

    Returns:
        A ReviewResult indicating whether the overall plan structure is approved.
    """
    user_prompt = (
        "以下の確定条件に対して、提案されたプランの全体構造（日程、ルート等）が条件を満たしているかチェックしてください。\n\n"
        "## ユーザーの入力（確定条件と希望条件）\n\n"
        f"{trip_input}\n\n"
        "## レビュー対象のプラン\n\n"
        f"{plan}"
    )

    # 全体チェックは検索不要なので OpenAI の高速/安価なモデルを使うか、Gemini の検索なしで実行
    provider = os.environ.get("REVIEWER_OVERALL_PROVIDER")
    model = os.environ.get("REVIEWER_OVERALL_MODEL")
    response = llm_client.generate(SYSTEM_PROMPT_OVERALL, user_prompt, use_search=False, provider=provider, model=model)
    return _parse_review_response(response)


def review_detailed(trip_input: str, plan: str) -> ReviewResult:
    """Review the detailed spots and existence in a generated plan.

    Args:
        trip_input: The full content of trip_input.md (constraints).
        plan: The generated plan to review.

    Returns:
        A ReviewResult indicating whether the detailed spots are approved.
    """
    user_prompt = (
        "以下の確定条件に対して、提案されたプランの詳細（実在性、設備要件等）が全ての条件を満たしているかチェックしてください。\n\n"
        "## ユーザーの入力（確定条件と希望条件）\n\n"
        f"{trip_input}\n\n"
        "## レビュー対象のプラン\n\n"
        f"{plan}"
    )

    # 詳細チェックは検索が必要なので Gemini を使う
    provider = os.environ.get("REVIEWER_DETAILED_PROVIDER")
    model = os.environ.get("REVIEWER_DETAILED_MODEL")
    response = llm_client.generate(SYSTEM_PROMPT_DETAILED, user_prompt, use_search=True, provider=provider, model=model)
    return _parse_review_response(response)
