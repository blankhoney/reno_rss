from app.providers.llm import create_provider


def test_create_provider_local_uses_openai_compatible_client(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "local")
    monkeypatch.setenv("LOCAL_LLM_BASE_URL", "http://127.0.0.1:9999/v1")
    monkeypatch.setenv("LOCAL_LLM_MODEL", "test-local")
    monkeypatch.setenv("LOCAL_LLM_API_KEY", "local-key")
    provider = create_provider()
    assert provider.__class__.__name__ == "MiniMaxProvider"
    assert provider.model_provider == "local"
    assert provider.client.config.base_url == "http://127.0.0.1:9999/v1"
    assert provider.client.config.model == "test-local"
