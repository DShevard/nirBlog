import os

import httpx
from dotenv import load_dotenv


load_dotenv()

api_key = os.environ["OPENROUTER_API_KEY"]
model = os.environ["OPENROUTER_MODEL"]

url = "https://openrouter.ai/api/v1/chat/completions"

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json",
}

data = {
    "model": model,
    "messages": [
        {
            "role": "user",
            "content": (
                "Объясни в двух предложениях, "
                "что такое BehaviorTree.CPP."
            ),
        }
    ],
    "max_tokens": 500,
}

try:
    response = httpx.post(
        url,
        headers=headers,
        json=data,
        timeout=120,
    )

    response.raise_for_status()

    result = response.json()
    answer = result["choices"][0]["message"]["content"]

    print("Ответ модели:")
    print(answer)

except httpx.HTTPStatusError as error:
    print(f"Ошибка API: {error.response.status_code}")
    print(error.response.text)

except httpx.RequestError as error:
    print(f"Ошибка соединения: {error}")
