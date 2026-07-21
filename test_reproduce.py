import os
import dotenv
from google import genai
from google.genai import types

dotenv.load_dotenv()
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

try:
    content = "This is a base context. " * 500
    cache = client.caches.create(
        model="gemini-3.5-flash",
        config=types.CreateCachedContentConfig(
            contents=[content]
        )
    )
    print("Cache created:", cache.name)
    
    # Try generating
    system_prompt = "You are a helpful planner."
    user_prompt = "Make a plan based on the context."
    combined_prompt = f"System: {system_prompt}\n\nUser: {user_prompt}"
    
    print("Sending generation request...")
    resp = client.models.generate_content(
        model="gemini-3.5-flash",
        contents=combined_prompt,
        config=types.GenerateContentConfig(
            cached_content=cache.name,
            temperature=0.7
        )
    )
    print("Generated:", resp.text)
    
    client.caches.delete(name=cache.name)
except Exception as e:
    import traceback
    traceback.print_exc()
