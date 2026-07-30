"""Inject a torn journal tail and recover checkpoint plus valid frame prefix."""

from tempfile import TemporaryDirectory

from minimongodb import Database


def main() -> None:
    with TemporaryDirectory(prefix="minimongodb-lab-") as directory:
        database = Database(directory)
        events = database.get_collection("events")
        events.insert_one({"_id": 1, "state": "checkpointed"})
        database.checkpoint()
        events.insert_one({"_id": 2, "state": "torn-tail-write"})
        print("before injected crash:", events.find())

        remaining = database.inject_journal_tail_truncation(3)
        print("truncated journal tail; remaining bytes:", remaining)

        recovered = Database(directory)
        print("recovered documents:", recovered.get_collection("events").find())
        print("  The checkpoint survives; the incomplete final frame is discarded.")


if __name__ == "__main__":
    main()
