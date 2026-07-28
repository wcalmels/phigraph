from phigraph.production import DataContract, validate_data_contracts
from .base import AgentContext, AgentResult

class DataContractAgent:
    name="data_contract"
    def run(self,context):
        tables=context.payload.get("tables",{})
        contracts=tuple(DataContract(**item) for item in context.payload.get("data_contracts",[]))
        if not contracts:
            contracts=tuple(DataContract(table=name,min_rows=1) for name in tables)
        result=validate_data_contracts(tables,contracts)
        context.artifacts["data_contract"]=result.to_dict()
        context.record(self.name,"validate_data_contracts",result.to_dict())
        return AgentResult(self.name,"ok" if result.passed else "blocked",
                           f"Data contract score {result.score:.3f}.",result.to_dict())
