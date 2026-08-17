"""PhiGraph Causal public API."""

from .graph import GraphDataset
from .spectral import SpectralAnalyzer, SpectralResult
from .localization import HotspotLocator
from .ablation import AblationEngine, AblationResult
from .corridors import CorridorAnalyzer
from .multiscale import MultiscaleOperator
from .agents import AgentContext, LocalCoordinator
from .domains import DomainProfile, get_domain_profile
from .modeling import AutoModelingAssistant, ModelingProposal
from .multifile_workflow import MultiFileConfig, run_multifile_modeling
from .analytical_workflow import (
    AnalyticalWorkflowConfig,
    run_analytical_multifile_workflow,
)

__all__ = [
    "GraphDataset",
    "SpectralAnalyzer",
    "SpectralResult",
    "HotspotLocator",
    "AblationEngine",
    "AblationResult",
    "CorridorAnalyzer",
    "MultiscaleOperator",
    "AgentContext",
    "LocalCoordinator",
    "DomainProfile",
    "get_domain_profile",
    "AutoModelingAssistant",
    "ModelingProposal",
    "MultiFileConfig",
    "run_multifile_modeling",
    "AnalyticalWorkflowConfig",
    "run_analytical_multifile_workflow",
    "OperationalWorkflowConfig",
    "run_operational_workflow",
    "MetaOperationalConfig",
    "run_meta_operational_workflow",
    "AdvancedMetaConfig",
    "run_advanced_meta_workflow",
    "BenchmarkConfig",
    "BenchmarkResult",
    "make_synthetic_fleet",
    "make_synthetic_fraud",
    "run_benchmark",
    "AdaptiveKernelConfig",
    "run_adaptive_kernel_workflow",
    "KernelMetaWorkflowConfig",
    "run_kernel_meta_workflow",
    "ProductionWorkflowConfig",
    "run_production_readiness_workflow",
    "GovernanceWorkflowConfig",
    "run_governed_production_workflow",
    "ShadowWorkflowConfig",
    "run_shadow_deployment_workflow",
    "AdvisoryWorkflowConfig",
    "run_controlled_advisory_workflow",
    "ExecutionSandboxWorkflowConfig",
    "run_execution_sandbox_workflow",
    "ReliabilityWorkflowConfig",
    "run_reliability_workflow",
    "DeploymentSettings",
    "load_settings",
    "create_app",
    "Database",
    "DatabaseSettings",
    "ArtifactRegistry",
    "JobQueue",
    "Worker",
    "DomainAdapter",
    "DomainRegistry",
    "DomainManifest",
    "GeneralPlatformRuntime",
]

from .operational_workflow import OperationalWorkflowConfig, run_operational_workflow

from .meta_workflow import MetaOperationalConfig, run_meta_operational_workflow

from .advanced_meta_workflow import AdvancedMetaConfig, run_advanced_meta_workflow

try:
    from .benchmark import (
        BenchmarkConfig,
        BenchmarkResult,
        make_synthetic_fleet,
        make_synthetic_fraud,
        run_benchmark,
    )
except ModuleNotFoundError:  # optional extra; API/pilot images may omit scikit-learn
    BenchmarkConfig = BenchmarkResult = None
    make_synthetic_fleet = make_synthetic_fraud = run_benchmark = None

from .kernel_workflow import AdaptiveKernelConfig, run_adaptive_kernel_workflow

from .kernel_meta_workflow import KernelMetaWorkflowConfig, run_kernel_meta_workflow

from .production_workflow import ProductionWorkflowConfig, run_production_readiness_workflow

from .governance_workflow import GovernanceWorkflowConfig, run_governed_production_workflow

from .shadow_workflow import ShadowWorkflowConfig, run_shadow_deployment_workflow

from .advisory_workflow import AdvisoryWorkflowConfig, run_controlled_advisory_workflow

from .execution_workflow import ExecutionSandboxWorkflowConfig, run_execution_sandbox_workflow

from .reliability_workflow import ReliabilityWorkflowConfig, run_reliability_workflow

from .deployment import (
    DeploymentSettings,
    load_settings,
    create_app,
)

from .platform import (
    Database,
    DatabaseSettings,
    ArtifactRegistry,
    JobQueue,
    Worker,
)

from .platform_general import DomainAdapter,DomainRegistry,DomainManifest,GeneralPlatformRuntime
