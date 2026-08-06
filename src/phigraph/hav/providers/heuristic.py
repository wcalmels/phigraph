from phigraph.hav.providers.base import BaseLLMProvider, ProviderResponse


class HeuristicProvider(BaseLLMProvider):
    provider_id = "heuristic"
    def generate(self, *, prompt: str, context: str = "") -> ProviderResponse:
        return ProviderResponse(
            text=f"{context}\n{prompt}".strip(),
            provider=self.provider_id,
            model="deterministic-echo-v1",
            metadata={"network_used": False},
        )
