from phigraph.platform_general import DomainManifest,FieldContract,TableContract
from .base_tabular import TabularDomainAdapter
class FraudAdapter(TabularDomainAdapter):
    def __init__(self):
        super().__init__(DomainManifest("fraud","1.0.0","Transaction and account intelligence",
        ("account","person","device","merchant","beneficiary","transaction"),
        ("owns","uses","transfers_to","pays","linked_to"),
        (TableContract("transactions",(FieldContract("account_id",nullable=False),FieldContract("beneficiary_id",nullable=False),
        FieldContract("amount",semantic_type="number"),FieldContract("timestamp",nullable=False))),),
        ("transaction_velocity","amount_zscore","device_rarity","beneficiary_risk"),
        ("review_transaction","review_account","create_fraud_case"),
        ("simulate_hold_transaction","simulate_freeze_account"),
        ("freeze_account_real","report_customer_automatically"),
        ("normalized","nonbacktracking","heat_050","temporal_025"),
        ("precision_at_k","fraud_capture_rate","customer_friction")),
        {},{"account_id":"account","beneficiary_id":"beneficiary"},
        ({"source":"account_id","target":"beneficiary_id","edge_type":"transfers_to"},))
