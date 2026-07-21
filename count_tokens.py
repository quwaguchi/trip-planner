import os
import dotenv
from google import genai

dotenv.load_dotenv()
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

with open('trip_input.md', 'r') as f:
    text = f.read()

resp = client.models.count_tokens(model="gemini-3.5-flash", contents=text)
print("Tokens:", resp.total_tokens)
