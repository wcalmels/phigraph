from phigraph.platform import (
    ArtifactRegistry,
    Database,
    DatabaseSettings,
    JobQueue,
    MigrationRunner,
    Principal,
    PromotionGate,
    PromotionRequest,
    Worker,
    authorize,
)


def test_registry_jobs_rbac_and_promotion(tmp_path):
    database = Database(
        DatabaseSettings(
            f"sqlite:///{tmp_path / 'platform.db'}"
        )
    )
    MigrationRunner(database).apply()

    registry = ArtifactRegistry(database)
    record = registry.register(
        artifact_type="kernel",
        name="heat",
        version="1.0",
        stage="shadow",
    )
    assert registry.list()[0].record_id == record.record_id

    queue = JobQueue(database)
    job = queue.enqueue(
        job_type="shadow_analysis",
        payload={"case_id": "x"},
    )
    worker = Worker(
        queue,
        {"shadow_analysis": lambda payload: {"case_id": payload["case_id"]}},
    )
    worker.run_once()
    assert job.status == "queued"

    assert authorize(
        Principal("alice", ("analyst",)),
        "jobs:create",
    )
    assert not authorize(
        Principal("bob", ("viewer",)),
        "jobs:create",
    )

    decision = PromotionGate().evaluate(
        PromotionRequest(
            record_id=record.record_id,
            from_stage="shadow",
            to_stage="staging",
            readiness_score=0.90,
            precision=0.85,
            false_positive_rate=0.10,
            audit_coverage=1.0,
            approvals=("operations", "safety"),
        )
    )
    assert decision["allowed"]

    production = PromotionGate().evaluate(
        PromotionRequest(
            record_id=record.record_id,
            from_stage="staging",
            to_stage="production",
            readiness_score=0.99,
            precision=0.99,
            false_positive_rate=0.01,
            audit_coverage=1.0,
            approvals=("operations", "safety"),
        )
    )
    assert not production["allowed"]
