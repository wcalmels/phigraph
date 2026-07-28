# TUCH PhiGraph Core v3.6.0

PhiGraph Code validation release. Adds deterministic repository indexing, an allow-listed compilation/test verifier, baseline-versus-governed benchmark evaluation, false-completion blocking, and a provider-neutral GitHub repository descriptor.

## Safety
The verifier does not accept arbitrary shell commands. It exposes only `compile` and `tests` checks. No remote repository mutation or external system modification is enabled.
