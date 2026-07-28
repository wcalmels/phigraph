from phigraph.meta import MetaLearningStore, score_run, recommend_configuration

def test_score_and_recommend(tmp_path):
    score = score_run(null_pvalue=0.02, robustness_score=0.8,
                      outcome_improved=True, relative_change=-0.2, runtime_seconds=5)
    assert 0 <= score.total <= 1
    store = MetaLearningStore(tmp_path/"meta.sqlite")
    for _ in range(3):
        store.add(domain="fleet",
                  config={"engineered_signal":"structural_deviation","min_join_overlap":0.25,"n_null_controls":30},
                  metrics=score.to_dict(), score=score.total, confirmed=True)
    rec = recommend_configuration(store.list(), domain="fleet")
    assert rec.support == 3
    assert not rec.exploration_required
