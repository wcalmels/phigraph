from phigraph.kernels import KernelContext
from phigraph.meta_kernel import (KernelExperimentStore,default_kernel_search_space,
    evaluate_kernel_candidate,extract_kernel_meta_context,recommend_kernel_configuration)
from .base import AgentContext, AgentResult

class KernelMetaLearningAgent:
    name="kernel_meta_learning"
    def run(self,context):
        dataset=context.artifacts.get("_projection_dataset")
        if dataset is None: return AgentResult(self.name,"blocked","Projection unavailable.",{})
        domain=str(context.payload.get("domain","general"))
        hetero=context.artifacts.get("_heterogeneous_graph_object")
        layers=0
        if hetero is not None:
            layers=len({str(d.get("edge_type","relation")) for *_,d in hetero.graph.edges(data=True)})
        meta=extract_kernel_meta_context(dataset,domain=domain,multiplex_layers=layers)
        candidates=default_kernel_search_space()
        store=KernelExperimentStore(context.payload.get("kernel_meta_store_path","data/kernel_meta_learning.sqlite"))
        decision=recommend_kernel_configuration(store.list(domain=domain),candidates,
            domain=domain,current_context=meta.to_dict(),
            exploration_strength=float(context.payload.get("kernel_exploration_strength",1.5)))
        selected=next(c for c in candidates if c.name==decision.selected_candidate["name"])
        evaluation=evaluate_kernel_candidate(selected,KernelContext(dataset=dataset,
            heterogeneous_graph=None if hetero is None else hetero.graph),
            spectral_modes=int(context.payload.get("spectral_modes",10)))
        record=store.add(domain=domain,context=meta.to_dict(),candidate=selected.to_dict(),
            metrics=evaluation.to_dict(),reward=evaluation.reward,
            confirmed=bool(context.payload.get("kernel_result_confirmed",False)))
        output={"context":meta.to_dict(),"decision":decision.to_dict(),
                "evaluation":evaluation.to_dict(),"experiment_id":record.experiment_id,
                "confirmed":record.confirmed}
        context.artifacts["kernel_meta_learning"]=output
        context.record(self.name,"select_evaluate_store_kernel",output)
        return AgentResult(self.name,"ok" if evaluation.valid else "warning",
            f"Selected {selected.name}.",output)
