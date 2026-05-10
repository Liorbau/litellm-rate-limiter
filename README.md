# LiteLLM proxy & rate limiter

<p>
    <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54" alt="Python" /></a>
    <a href="https://docs.litellm.ai/"><img src="https://img.shields.io/badge/LiteLLM_Proxy-6366f1?style=for-the-badge" alt="LiteLLM Proxy" /></a>
</p>

This repo exercises a realistic LiteLLM proxy setup. Multiple provider deployments and client.

**Stack:** LiteLLM (`litellm_config.yaml`) · asyncio client (`rate_limiter.py`) · smoke tests (`test_config.py`).

## Quick start

1. Copy `.env.example` → `.env` and set `LITELLM_MASTER_KEY`, `TEAM_A_API_KEY`, `TEAM_B_API_KEY`. Export vars into your shell (Unix: `set -a && source .env`; Windows: load the same keys into the environment before running Docker/Python).

2. **Proxy (Docker):**

```bash
docker run --rm -p 4000:4000 \
  -v "${PWD}/litellm_config.yaml:/app/config.yaml" \
  -e LITELLM_MASTER_KEY -e TEAM_A_API_KEY -e TEAM_B_API_KEY \
  ghcr.io/berriai/litellm:main-latest \
  --config /app/config.yaml --detailed_debug
```

3. **Python:** `python -m venv .venv && source .venv/bin/activate` (Windows: `.venv\Scripts\activate`) · `pip install -r requirements.txt`

4. With the proxy on `http://localhost:4000`: `python test_config.py` then `python rate_limiter.py`.

