"""PhiGraph Code product package.

This namespace separates software-agent evaluation from the domain-neutral core.
"""
from phigraph.core_v3.code_benchmark import (
    AgentReport, CodeVerifier, GitHubRepositoryDescriptor, MultiModelBenchmarkSuite,
    PhiGraphCodeBenchmark, RepositoryIndexer,
)
from phigraph.core_v3.code_v38 import (
    CommitSnapshotBuilder, ModelAdapter, PatchEvaluator, PatchProposal,
    StaticModelAdapter, RequirementTraceBuilder, RequirementTraceGraph,
)
from phigraph.core_v3.code_v39 import (
    CorpusExperimentRunner, CorpusTask, DependencyInventory,
    DeterministicSecurityScanner, GitHubCommitArchiveFetcher,
    OpenAICompatibleModelAdapter, PatchQualityEvaluator, ReproducibleCorpus,
    save_scientific_report,
)

__all__ = [name for name in globals() if not name.startswith("_")]
