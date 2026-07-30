"""Show why an action update becomes a final assignment in the oplog."""

from minimongodb import Collection, Oplog, replay


def main() -> None:
    source = Collection("counters")
    source.insert_one({"_id": "visits", "count": 2})
    requested = {"$inc": {"count": 3}}
    source.update_one({"_id": "visits"}, requested)
    update_entry = list(source.oplog)[-1]

    print("requested $inc:", requested)
    print("stored oplog payload:", update_entry.payload)
    print("  Repeating $inc would add twice; repeating $set converges on count=5.")

    target = Collection("counters", oplog=Oplog())
    replay(source.oplog, target)
    once = target.find()
    replay(source.oplog, target)
    twice = target.find()
    print("after one replay:", once)
    print("after two replays:", twice)
    print("same after replay twice:", once == twice)


if __name__ == "__main__":
    main()
