#!/usr/bin/env python3
"""Road trip planner CLI – interactive loop for generating and reviewing plans."""

from __future__ import annotations

import sys

import feedback_processor
import llm_client
import markdown_io
import planner
import reviewer

# Maximum number of Reviewer retries before giving up
MAX_REVIEW_RETRIES = 3


def print_header() -> None:
    """Print the application header."""
    print()
    print("━" * 50)
    print("  🚐 ロードトリップ旅程プランナー AI")
    print("━" * 50)
    print()


def show_plan(plan: str) -> None:
    """Save the plan to a file, open it, and show a summary in the terminal."""
    title = markdown_io.save_current_plan(plan)
    print()
    print(f"📍 プランを current_plan.md に保存し、開きました。")
    print(f"   タイトル: {title}")


def get_user_choice() -> str:
    """Prompt the user for their decision on the plan.

    Returns:
        One of 'ok', 'ng', or 'quit'.
    """
    print()
    print("このプランはいかがですか？")
    print("  [OK]   承認してプラン一覧に追加")
    print("  [NG]   フィードバックを入力して再生成")
    print("  [quit] 終了")
    print()

    while True:
        choice = input("> ").strip().lower()
        if choice in ("ok", "ng", "quit", "q"):
            return "quit" if choice == "q" else choice
        print("⚠️  OK / NG / quit のいずれかを入力してください。")


def get_feedback() -> str:
    """Prompt the user for feedback via an external editor.

    Returns:
        The feedback text.
    """
    print()
    print("❓ NGの理由をエディタで入力してください...")
    print("   (エディタを保存して閉じると続行します)")
    feedback = markdown_io.get_user_feedback_via_editor()
    if not feedback:
        print("⚠️  フィードバックが空です。元の条件で再生成します。")
    return feedback


def generate_and_review(trip_input: str) -> str | None:
    """Generate a plan and pass it through the multi-stage reviewer.

    Retries up to MAX_REVIEW_RETRIES times if the reviewer rejects the plan.

    Args:
        trip_input: The full content of trip_input.md.

    Returns:
        The approved plan text, or None if all retries are exhausted.

    Raises:
        llm_client.APIError: If the API call fails.
    """
    overall_issues: list[str] | None = None
    detailed_issues: list[str] | None = None
    plan: str | None = None
    
    # Try to create a shared cache for the trip_input context (used if Gemini is configured)
    cache_name = None
    try:
        cache_name = llm_client.create_shared_cache(trip_input)
    except Exception as e:
        print(f"⚠️  [System] キャッシュの作成に失敗しました。通常の生成を続行します: {e}")

    try:
        for attempt in range(1, MAX_REVIEW_RETRIES + 1):
            if attempt == 1:
                print("🤖 [Planner] プランを生成中...")
                plan = planner.generate_plan(trip_input, cache_name=cache_name)
            elif overall_issues:
                print(f"🤖 [Planner] プラン全体を再生成中...（{attempt}/{MAX_REVIEW_RETRIES}）")
                plan = planner.generate_plan(trip_input, overall_issues, cache_name=cache_name)
            elif detailed_issues and plan is not None:
                print(f"🤖 [Planner] プランの部分修正を実行中...（{attempt}/{MAX_REVIEW_RETRIES}）")
                plan = planner.refine_plan(plan, trip_input, detailed_issues, cache_name=cache_name)
    
            # Clear issues for this attempt
            overall_issues = None
            detailed_issues = None
    
            # Stage 1: Overall Review
            print("🔍 [Reviewer] 全体チェックを実行中...")
            overall_result = reviewer.review_overall(trip_input, plan, cache_name=cache_name)
    
            if not overall_result.approved:
                print(f"⚠️  [Reviewer] 全体チェック不合格（試行 {attempt}/{MAX_REVIEW_RETRIES}）")
                for issue in overall_result.issues:
                    print(f"   ・{issue}")
                overall_issues = overall_result.issues
                continue
    
            # Stage 2: Detailed Review
            print("🔍 [Reviewer] 詳細チェック（実在性・設備）を実行中...")
            detailed_result = reviewer.review_detailed(trip_input, plan, cache_name=None)
    
            if not detailed_result.approved:
                print(f"⚠️  [Reviewer] 詳細チェック不合格（試行 {attempt}/{MAX_REVIEW_RETRIES}）")
                for issue in detailed_result.issues:
                    print(f"   ・{issue}")
                detailed_issues = detailed_result.issues
                continue
    
            print("✅ [Reviewer] 全レビュー通過！")
            return plan
    
        print()
        print("❌ レビューを通過できませんでした。")
        print("   trip_input.md の確定条件を見直すか、再実行してください。")
        return None
    finally:
        if cache_name:
            llm_client.delete_cache(cache_name)


def ask_continue() -> bool:
    """Ask the user whether to generate another plan.

    Returns:
        True if the user wants to continue, False otherwise.
    """
    print()
    print("続けて別のプランを生成しますか？ [yes/no]")
    while True:
        choice = input("> ").strip().lower()
        if choice in ("yes", "y", "はい"):
            return True
        if choice in ("no", "n", "いいえ", "quit", "q"):
            return False
        print("⚠️  yes / no のいずれかを入力してください。")


def main() -> None:
    """Main CLI loop."""
    print_header()

    # Read trip input
    try:
        trip_input = markdown_io.read_trip_input()
    except FileNotFoundError as e:
        print(f"❌ {e}")
        sys.exit(1)

    print("📋 trip_input.md を読み込みました。")

    while True:
        # Generate & Review loop
        try:
            plan = generate_and_review(trip_input)
        except (llm_client.APIError, EnvironmentError) as e:
            print(f"\n❌ {e}")
            sys.exit(1)

        if plan is None:
            break

        # Show the plan to the user
        show_plan(plan)

        # Get user decision
        choice = get_user_choice()

        if choice == "quit":
            print("\n👋 お疲れさまでした！良い旅を！")
            break

        elif choice == "ok":
            plan_number = markdown_io.count_approved_plans() + 1
            saved_path = markdown_io.save_approved_plan(plan, plan_number)
            print(f"\n🎉 プラン #{plan_number} を {saved_path} に保存しました！")

            if not ask_continue():
                print("\n👋 お疲れさまでした！良い旅を！")
                break

            # Reload trip_input for the next iteration (in case of prior feedback additions)
            trip_input = markdown_io.read_trip_input()

        elif choice == "ng":
            raw_feedback = get_feedback()
            if raw_feedback:
                print("\n🧠 [Processor] フィードバックを要件に変換中...")
                try:
                    structured_feedback = feedback_processor.process_feedback(raw_feedback, plan, trip_input)
                    markdown_io.append_feedback(structured_feedback)
                    print("📝 構造化された要件を trip_input.md に追記しました:\n")
                    print(structured_feedback)
                except (llm_client.APIError, EnvironmentError) as e:
                    print(f"\n❌ フィードバックの処理中にエラーが発生しました: {e}")
                    sys.exit(1)
            else:
                print("\n📝 フィードバックなしで再生成します。")

            # Reload the updated trip_input
            trip_input = markdown_io.read_trip_input()


if __name__ == "__main__":
    main()
