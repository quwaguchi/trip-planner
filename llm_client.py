"""LLM API wrapper for the trip planner with retry and error handling (supports OpenAI and Gemini)."""

import os
import time

import dotenv

# Load environment variables from .env file
dotenv.load_dotenv()

# Retry configuration
MAX_RETRIES = 5
INITIAL_BACKOFF_SECONDS = 3.0
BACKOFF_MULTIPLIER = 2.0


class APIError(Exception):
    """Custom exception for API errors with user-friendly messages."""
    pass


def _get_provider() -> str:
    """Return the configured LLM provider (openai or gemini)."""
    return os.environ.get("LLM_PROVIDER", "openai").lower()


def _generate_with_gemini(system_prompt: str, user_prompt: str, use_search: bool = False, model: str | None = None) -> str:
    from google import genai
    from google.genai import errors as genai_errors

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "環境変数 GEMINI_API_KEY が設定されていません。\n"
            "  .env ファイルに GEMINI_API_KEY を設定してください。"
        )
    client = genai.Client(api_key=api_key)
    current_model = model or os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
    backoff = INITIAL_BACKOFF_SECONDS
    
    config_args = {
        "system_instruction": system_prompt,
        "temperature": 0.7,
    }
    if use_search:
        config_args["tools"] = [{"google_search": {}}]

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.models.generate_content(
                model=current_model,
                contents=user_prompt,
                config=genai.types.GenerateContentConfig(**config_args),
            )
            return response.text

        except genai_errors.ClientError as e:
            if e.code == 429:
                if attempt == MAX_RETRIES:
                    raise APIError("Gemini APIレートリミットに達しました。") from e
                print(f"   ⏳ レートリミット ({current_model})。{backoff:.0f}秒後にリトライ ({attempt}/{MAX_RETRIES})...")
                time.sleep(backoff)
                backoff *= BACKOFF_MULTIPLIER
            else:
                raise APIError(f"Gemini APIエラー (HTTP {e.code}): {e}") from e

        except genai_errors.ServerError as e:
            if attempt == MAX_RETRIES:
                raise APIError(f"Gemini APIサーバーエラー ({current_model}): {e}") from e
            print(f"   ⏳ サーバーエラー ({current_model})。{backoff:.0f}秒後にリトライ ({attempt}/{MAX_RETRIES})...")
            time.sleep(backoff)
            backoff *= BACKOFF_MULTIPLIER

    raise APIError("Gemini APIの予期しないエラーが発生しました。")


def _generate_with_openai(system_prompt: str, user_prompt: str, model: str | None = None) -> str:
    import openai

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "環境変数 OPENAI_API_KEY が設定されていません。\n"
            "  .env ファイルに OPENAI_API_KEY を設定してください。"
        )
    client = openai.OpenAI(api_key=api_key)
    current_model = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    backoff = INITIAL_BACKOFF_SECONDS

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            kwargs = {
                "model": current_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            }
            
            # gpt-5 などの特定モデルはtemperatureの指定をサポートしないため除外
            if not current_model.startswith("gpt-5"):
                kwargs["temperature"] = 0.7
                
            kwargs["stream"] = True
            response = client.chat.completions.create(**kwargs)
            content = ""
            for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    content += chunk.choices[0].delta.content
            
            if content == "":
                raise APIError("OpenAI APIから空のレスポンスが返されました。")
            return content

        except openai.RateLimitError as e:
            if attempt == MAX_RETRIES:
                raise APIError("OpenAI APIレートリミットに達しました。") from e
            print(f"   ⏳ レートリミット。{backoff:.0f}秒後にリトライ ({attempt}/{MAX_RETRIES})...")
            time.sleep(backoff)
            backoff *= BACKOFF_MULTIPLIER
            
        except openai.APIError as e:
            if attempt == MAX_RETRIES:
                raise APIError(f"OpenAI APIサーバーエラー: {e}") from e
            print(f"   ⏳ サーバーエラー。{backoff:.0f}秒後にリトライ ({attempt}/{MAX_RETRIES})...")
            time.sleep(backoff)
            backoff *= BACKOFF_MULTIPLIER

    raise APIError("OpenAI APIの予期しないエラーが発生しました。")


def generate(system_prompt: str, user_prompt: str, use_search: bool = False, provider: str | None = None, model: str | None = None) -> str:
    """Call the configured LLM API and return the text response.

    Args:
        system_prompt: The system instruction for the model.
        user_prompt: The user message to send.
        use_search: If True, enables Grounding (Gemini only).
        provider: Optional. Explicitly specify 'openai' or 'gemini'. If None, uses LLM_PROVIDER from .env.
        model: Optional. Explicitly specify the model name. If None, uses the provider's default from .env.

    Returns:
        The model's text response.

    Raises:
        APIError: If the API call fails after all retries.
    """
    if provider is None:
        provider = _get_provider()
    provider = provider.lower()
    
    if provider == "gemini":
        return _generate_with_gemini(system_prompt, user_prompt, use_search, model=model)
    elif provider == "openai":
        if use_search:
            print("   ⚠️ OpenAIモデルでは検索グラウンディングはサポートされていないため、無効化されます。")
        return _generate_with_openai(system_prompt, user_prompt, model=model)
    else:
        raise EnvironmentError(f"未知の LLM_PROVIDER が指定されました: {provider}")
