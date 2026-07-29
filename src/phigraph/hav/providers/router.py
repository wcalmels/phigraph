from phigraph.hav.providers.base import BaseLLMProvider, ProviderResponse


class ProviderRouter:
    def __init__(self, providers: list[BaseLLMProvider]) -> None:
        if not providers:
            raise ValueError("at least one provider is required")
        self.providers = {p.provider_id: p for p in providers}
    def generate(self, *, provider_id: str, prompt: str, context: str = "") -> ProviderResponse:
        if provider_id not in self.providers:
            raise KeyError(f"unknown provider: {provider_id}")
        return self.providers[provider_id].generate(prompt=prompt, context=context)
