from phigraph.meta.temporal_cv import expanding_window_folds, temporal_cross_validate

def test_expanding_window_no_leakage():
    folds = expanding_window_folds(12, min_train_size=6, test_size=2)
    assert folds
    assert all(fold.train_end == fold.test_start for fold in folds)

    result = temporal_cross_validate(
        list(range(12)),
        scorer=lambda train, test: 1.0,
        min_train_size=6,
        test_size=2,
    )
    assert result.leakage_guard
    assert result.mean_score == 1.0
