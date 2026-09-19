from openai import OpenAI
from config.settings import openai_api_key, model_name

client = OpenAI(api_key=openai_api_key)


def get_root_cause(error_text: str) -> str:
    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "user", "content": f"What is the likely root cause of this pipeline failure?\n\n{error_text}"}
        ],
    )
    return response.choices[0].message.content