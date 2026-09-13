import os
from dotenv import load_dotenv

load_dotenv()

openai_api_key = os.environ.get("OPENAI_API_KEY", "")
model_name = "gpt-5.6-luna"