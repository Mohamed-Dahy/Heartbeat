"""The providers we check.

Each URL is a real API endpoint. We send no API key, so they answer 401 —
which proves the server is awake. See the 401 rule in probe.py.
"""

PROVIDERS = {
    "openai": "https://api.openai.com/v1/models",
    "anthropic": "https://api.anthropic.com/v1/models",
    "mistral": "https://api.mistral.ai/v1/models",
    "groq": "https://api.groq.com/openai/v1/models",
}
