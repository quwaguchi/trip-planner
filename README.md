# 🚐 ロードトリップ旅程プランナー AI

OpenAI API (GPT-4o-mini) または Gemini API を使ったロードトリップの旅程計画AIツール。制約条件と希望をMarkdownで記述すると、Planner AI がプランを生成し、Reviewer AI がチェックした上でユーザーに提示します。

## セットアップ

### 1. Python 仮想環境の作成

```bash
cd trip-planner
python3 -m venv .venv
source .venv/bin/activate
```

### 2. 依存パッケージのインストール

```bash
pip install -r requirements.txt
```

### 3. 環境変数（APIキー）の設定

本ツールは `.env` ファイルを用いて設定を管理します。

1. テンプレートをコピーして `.env` を作成します:
```bash
cp .env.example .env
```
2. `.env` ファイルをテキストエディタで開き、APIキーを設定してください。デフォルトでは OpenAI (GPT-4o-mini) が使用されます。

```ini
# 例
LLM_PROVIDER=openai
OPENAI_API_KEY='your-openai-api-key-here'
OPENAI_MODEL=gpt-4o-mini
```

Geminiを使用したい場合は、`LLM_PROVIDER=gemini` に変更し、`GEMINI_API_KEY` を設定してください。

## 使い方

### 1. 旅行計画の入力

`trip_input.md` を編集して、あなたのロードトリップの条件を記入します:

```markdown
# ロードトリップ計画

## 確定条件（必ず守ること）

- 日程: 2026年8月10日〜8月14日（4泊5日）
- 出発地: 東京
- 到着地: 東京（往復）
- 車種: キャンピングカー
- 立ち寄りスポットには必ずGoogle Mapsのリンクを付けること

## 希望条件（できれば叶えたいこと）

- 綺麗な自然を見たい
- 温泉に入りたい
- 地元のグルメを楽しみたい
```

### 2. プランナーの実行

```bash
python main.py
```

### 3. 対話フロー

```
🤖 プランを生成中...
🔍 レビュー中...
✅ レビュー通過！

📍 ロードトリッププラン
（プラン表示）

このプランはいかがですか？
  [OK]   承認してプラン一覧に追加
  [NG]   フィードバックを入力して再生成
  [quit] 終了
```

- **OK**: プランが `approved_plan/` ディレクトリ内に保存されます
- **NG**: 理由を入力すると `trip_input.md` に自動追記され、プランが再生成されます
- **quit**: 終了します

## ファイル構成

| ファイル | 説明 |
|---|---|
| `main.py` | CLIメインループ |
| `planner.py` | プラン生成 AI |
| `reviewer.py` | 制約チェック AI |
| `llm_client.py` | LLM API ラッパー (OpenAI / Gemini) |
| `markdown_io.py` | Markdown読み書き |
| `trip_input.md` | 旅行条件の入力ファイル（ユーザー編集） |
| `approved_plan/` | 承認済みプランが保存されるディレクトリ（自動生成） |
| `.env.example` | 環境変数の設定テンプレート |
