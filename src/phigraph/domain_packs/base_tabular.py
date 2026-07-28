from phigraph.platform_general import DomainAdapter,AdapterOutput

class TabularDomainAdapter(DomainAdapter):
    def __init__(self,manifest,aliases,entity_mappings,relation_mappings):
        self.manifest=manifest
        self.aliases=aliases
        self.entity_mappings=entity_mappings
        self.relation_mappings=relation_mappings

    def validate(self,tables):
        normalized={
            name:frame.rename(columns=self.aliases.get(name,{})).copy()
            for name,frame in tables.items()
        }
        return super().validate(normalized)

    def normalize(self,tables):
        norm={
            name:frame.rename(
                columns=self.aliases.get(name,{})
            ).copy()
            for name,frame in tables.items()
        }
        return AdapterOutput(
            self.manifest.name,
            norm,
            self.entity_mappings,
            self.relation_mappings,
            self.manifest.signal_catalog,
            {
                "advisory":self.manifest.allowed_advisory_actions,
                "sandbox":self.manifest.allowed_sandbox_actions,
                "prohibited":self.manifest.prohibited_actions,
            },
            {
                "adapter_version":self.manifest.version,
                "kernel_candidates":self.manifest.default_kernel_candidates,
                "success_metrics":self.manifest.success_metrics,
            },
        )
