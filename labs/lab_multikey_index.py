"""Show how one array-bearing document contributes several index keys."""

from minimongodb import Collection


def main() -> None:
    articles = Collection("articles")
    articles.insert_many(
        [
            {"_id": 1, "title": "Storage notes", "tags": ["database", "storage"]},
            {"_id": 2, "title": "Python notes", "tags": ["python", "database"]},
            {"_id": 3, "title": "Networks", "tags": ["networking"]},
        ]
    )
    index_name = articles.create_index("tags")
    metadata = articles.index_information()[index_name]

    print("one document can contribute several multikey index entries")
    print("index keys:", metadata["entries"], "multikey:", metadata["multikey"])
    matched = articles.find({"tags": "database"})
    print("matched document ids:", [document["_id"] for document in matched])


if __name__ == "__main__":
    main()
