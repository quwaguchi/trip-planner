import os
import dotenv
from google import genai

dotenv.load_dotenv()
api_key = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

try:
    response = client.models.generate_content(
        model="gemini-3.5-flash",
        contents="Hello",
        config=genai.types.GenerateContentConfig(
            tools=[{"google_search": {}}]
        )
    )
    print("Success!")
except Exception as e:
    print(f"Exception type: {type(e)}")
    print(f"Exception: {e}")
