"""Contrast array auto-matching with exact nested-document matching."""

from minimongodb import Collection


def main() -> None:
    people = Collection("people")
    people.insert_one(
        {
            "_id": 1,
            "name": "Ada",
            "tags": ["database", "python"],
            "profile": {"city": "London", "role": "engineer"},
        }
    )

    scalar = people.find({"tags": "python"})
    literal = people.find({"profile": {"city": "London"}})
    dotted = people.find({"profile.city": "London"})

    print("scalar array match:", [doc["name"] for doc in scalar])
    print("  A scalar query inspects each stored array element automatically.")
    print("literal nested document:", [doc["name"] for doc in literal])
    print("  A document literal means exact whole-document equality; extra keys matter.")
    print("dotted path match:", [doc["name"] for doc in dotted])
    print("  A dotted path selects one nested field, so unrelated keys do not matter.")


if __name__ == "__main__":
    main()
