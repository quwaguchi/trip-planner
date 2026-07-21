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


def create_shared_cache(content: str) -> str | None:
    """Create a shared Gemini Cache resource for a given base content.
    
    Returns the cache name, or None if the default provider is not Gemini.
    """
    if _get_provider() != "gemini":
        return None

    from google import genai
    from google.genai import types

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None
        
    client = genai.Client(api_key=api_key)
    model = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
    
    # Check token count
    resp = client.models.count_tokens(model=model, contents=content)
    token_count = resp.total_tokens
    
    # ---------------------------------------------------------
    # TODO(Padding-Removal): GeminiのキャッシュAPIは仕様上「最低1024トークン」が必要です。
    # trip_input.md の内容が豊富になり、自然に 1024 トークンを超えるようになった場合、
    # または Gemini API の仕様変更で最小要件が撤廃された場合は、
    # 以下の padding ロジックを安全に削除してください。
    # ---------------------------------------------------------
    if token_count < 1024:
        # 1024トークンに到達するまでパディングを追加 (余裕を見て少し多めに追加)
        padding_text = "\n" + "<!-- cache padding text to satisfy minimum token requirement -->\n" * 150
        content += padding_text
    
    # Create cache (NO tools, NO system_instruction to avoid RemoteProtocolError/503 issues)
    cache = client.caches.create(
        model=model,
        config=types.CreateCachedContentConfig(
            contents=[content]
        )
    )
    return cache.name


def delete_cache(cache_name: str | None) -> None:
    """Delete a Gemini Cache resource."""
    if not cache_name or _get_provider() != "gemini":
        return
        
    from google import genai
    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        client = genai.Client(api_key=api_key)
        try:
            client.caches.delete(name=cache_name)
        except Exception as e:
            print(f"   ⚠️ キャッシュの削除に失敗しました: {e}")


def _generate_with_gemini(system_prompt: str, user_prompt: str, use_search: bool = False, model: str | None = None, cache_name: str | None = None) -> str:
    import httpx
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
        "temperature": 0.9,
    }
    
    # もし明示的キャッシュ(cache_name)を使う場合は、
    # システムプロンプトをユーザープロンプトの先頭に手動で結合し、config側のシステムプロンプト設定は行わない
    if cache_name:
        config_args["cached_content"] = cache_name
        user_prompt = f"System: {system_prompt}\n\nUser: {user_prompt}"
    else:
        config_args["system_instruction"] = system_prompt
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
            
        except httpx.RequestError as e:
            if attempt == MAX_RETRIES:
                raise APIError(f"Gemini APIネットワークエラー ({current_model}): {e}") from e
            print(f"   ⏳ ネットワークエラー ({type(e).__name__})。{backoff:.0f}秒後にリトライ ({attempt}/{MAX_RETRIES})...")
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


def generate(system_prompt: str, user_prompt: str, use_search: bool = False, provider: str | None = None, model: str | None = None, cache_name: str | None = None) -> str:
    """Call the configured LLM API and return the text response.

    Args:
        system_prompt: The system instruction for the model.
        user_prompt: The user message to send.
        use_search: If True, enables Grounding (Gemini only).
        provider: Optional. Explicitly specify 'openai' or 'gemini'. If None, uses LLM_PROVIDER from .env.
        model: Optional. Explicitly specify the model name. If None, uses the provider's default from .env.
        cache_name: Optional. Explicitly specify the Gemini Cache name to reuse context.

    Returns:
        The model's text response.

    Raises:
        APIError: If the API call fails after all retries.
    """
    if provider is None:
        provider = _get_provider()
    provider = provider.lower()
    
    if provider == "gemini":
        return _generate_with_gemini(system_prompt, user_prompt, use_search, model=model, cache_name=cache_name)
    elif provider == "openai":
        if use_search:
            print("   ⚠️ OpenAIモデルでは検索グラウンディングはサポートされていないため、無効化されます。")
        return _generate_with_openai(system_prompt, user_prompt, model=model)
    else:
        raise EnvironmentError(f"未知の LLM_PROVIDER が指定されました: {provider}")
