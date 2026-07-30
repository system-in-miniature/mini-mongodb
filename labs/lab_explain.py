"""Compare the same selective query before and after index construction."""

from minimongodb import Collection


def main() -> None:
    events = Collection("events")
    events.insert_many(
        [
            {"_id": 1, "kind": "rare"},
            {"_id": 2, "kind": "common"},
            {"_id": 3, "kind": "common"},
            {"_id": 4, "kind": "common"},
        ]
    )
    query = {"kind": "rare"}

    before = events.explain(query)
    print("before index:", before["queryPlanner"]["winningPlan"]["stage"])
    print("docs examined:", before["executionStats"]["docsExamined"])

    events.create_index("kind")
    after = events.explain(query)
    print("after index:", after["queryPlanner"]["winningPlan"]["stage"])
    print("docs examined:", after["executionStats"]["docsExamined"])


if __name__ == "__main__":
    main()
