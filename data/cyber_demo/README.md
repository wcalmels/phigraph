# Cybersecurity demo data

Generate the current demo dataset with:

```python
from phigraph.cyber_mvp import generate_demo_events

generate_demo_events().to_csv(
    "data/cyber_demo/security_events.csv",
    index=False,
)
```

The final records contain a labeled synthetic attack chain for functional
testing. They are not evidence of real-world detection performance.
