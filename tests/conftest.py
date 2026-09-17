import os

# app.py builds an OpenAI() client at import time, which requires an API key
# to be present (it doesn't validate it). Fall back to a dummy key so the
# test suite doesn't depend on a real .env / network access.
os.environ.setdefault("OPENAI_API_KEY", "sk-test-dummy-key-for-tests")
