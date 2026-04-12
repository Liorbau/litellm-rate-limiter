"""Smoke tests against the LiteLLM proxy (run after the proxy is up on port 4000)."""

import os

from openai import OpenAI

_master = os.environ.get("LITELLM_MASTER_KEY")
if not _master:
    raise RuntimeError("Set LITELLM_MASTER_KEY to match the LiteLLM proxy.")

client = OpenAI(
    api_key=_master,
    base_url="http://localhost:4000",
)

def test_basic_completion():
    print("Testing basic completion...")
    response = client.chat.completions.create(
        model="my-model",
        messages=[{"role": "user", "content": "Say hello in one word."}],
    )
    print(f"  Response: {response.choices[0].message.content}")
    return response


def test_multiple_requests():
    print(f"\nSending 5 sequential requests...")
    successes = 0
    for i in range(5):
        try:
            response = client.chat.completions.create(
                model="my-model",
                messages=[{"role": "user", "content": f"Count to {i+1}"}],
            )
            successes += 1
            print(f"  Request {i+1}: OK")
        except Exception as e:
            print(f"  Request {i+1}: FAILED — {e}")

    print(f"\nResult: {successes}/5 succeeded")
    if successes == 5:
        print("PASS — Config is working correctly!")
    else:
        print("FAIL — Check your config for errors.")


if __name__ == "__main__":
    test_basic_completion()
    test_multiple_requests()
