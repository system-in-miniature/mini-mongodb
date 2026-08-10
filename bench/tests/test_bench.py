from bench.run import build_results


def test_selective_index_reduces_examined_documents_without_changing_results() -> None:
    results = build_results()
    for point in results["measurements"]:
        assert point["before_stage"] == "COLLSCAN"
        assert point["after_stage"] == "IXSCAN"
        assert point["work_reduction"] == 100.0
        assert point["results_equal"] is True
