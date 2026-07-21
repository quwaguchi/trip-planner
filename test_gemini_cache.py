import os
import dotenv
from google import genai
from google.genai import types

dotenv.load_dotenv()
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

# Create a dummy large content to pass the 1024 token minimum
large_content = "This is a base context. " * 500

try:
    # Create cache WITH tools, but WITHOUT system_instruction
    cache = client.caches.create(
        model="gemini-3.5-flash",
        config=types.CreateCachedContentConfig(
            contents=[large_content],
            tools=[{"google_search": {}}]
        )
    )
    print("Cache created successfully:", cache.name)
    
    # Call 1: Planner style (prepend system prompt to user prompt)
    planner_prompt = "System: You are a planner.\nUser: Make a plan."
    resp1 = client.models.generate_content(
        model="gemini-3.5-flash",
        contents=planner_prompt,
        config=types.GenerateContentConfig(
            cached_content=cache.name,
            # NO system_instruction, NO tools here
        )
    )
    print("Planner response length:", len(resp1.text))
    
    # Call 2: Reviewer style (prepend system prompt to user prompt)
    reviewer_prompt = "System: You are a reviewer.\nUser: Review this."
    resp2 = client.models.generate_content(
        model="gemini-3.5-flash",
        contents=reviewer_prompt,
        config=types.GenerateContentConfig(
            cached_content=cache.name,
            # NO system_instruction, NO tools here
        )
    )
    print("Reviewer response length:", len(resp2.text))
    
    # Clean up
    client.caches.delete(name=cache.name)
except Exception as e:
    print("Error:", type(e), e)
