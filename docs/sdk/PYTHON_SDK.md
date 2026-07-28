# PhiGraph Python SDK

```python
from phigraph.sdk import PhiGraphClient

client = PhiGraphClient(
    "https://phigraph.example.com",
    bearer_token="...",
    tenant_id="acme",
    project_id="code-agent",
)
status = client.status()
claim = client.create_claim({
    "statement": "All tests pass",
    "claim_type": "test_run",
    "subject": "repo@commit",
    "issuer": "coding-agent",
})
```

The SDK sends tenant/project scope on every request and supports idempotency keys for writes.
