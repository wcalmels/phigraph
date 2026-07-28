import pandas as pd
from phigraph.kernel_meta_workflow import *

def test_workflow(tmp_path):
    tables={"fuel":pd.DataFrame({"camion":[f"KLG-{100+i%8}" for i in range(32)],
        "surtidor":[f"S{i%3}" for i in range(32)],"litros":[400+i for i in range(32)]}),
        "trips":pd.DataFrame({"equipo":[str(100+i%8) for i in range(32)],
        "ruta":[f"R{i%4}" for i in range(32)],"toneladas":[100+i%10 for i in range(32)]})}
    r=run_kernel_meta_workflow(tables,KernelMetaWorkflowConfig(domain="fleet",
        kernel_meta_store_path=str(tmp_path/"m.sqlite"),kernel_result_confirmed=True))
    assert r["results"][-1]["agent"]=="kernel_meta_learning"
    assert "decision" in r["artifacts"]["kernel_meta_learning"]
