from phigraph.reliability import *
def test_reliability(tmp_path):
    assert run_health_checks(data_path=tmp_path).healthy
    m=MetricsRegistry()
    with m.timer("x"): pass
    assert m.snapshot()["timings"]["x"]["count"]==1
    t=TraceRecorder(tmp_path/"t.json"); t.record("x"); assert len(t.list())==1
    b=CircuitBreaker(failure_threshold=2); b.failure(); b.failure(); assert not b.allow()
    n={"x":0}
    def f():
        n["x"]+=1
        if n["x"]<2: raise RuntimeError()
        return 1
    v,a=run_with_retry(f,policy=RetryPolicy(max_attempts=2,initial_delay_seconds=0))
    assert v==1 and a==2
