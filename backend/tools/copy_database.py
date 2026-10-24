"""Make a full copy of the Reachwise database, for trying out risky changes safely.

Run from the backend folder:
    .venv\\Scripts\\python -m tools.copy_database reachwise_test

It copies every collection (students, professors, emails, uploaded files...) from the
database named in .env (MONGODB_DB) into the new name. Point a test copy of the backend
at it by setting MONGODB_DB=reachwise_test in that folder's .env. The original is not changed.
"""
import sys

from pymongo import MongoClient

from app.config import settings


def main():
    if len(sys.argv) != 2:
        sys.exit("Usage: python -m tools.copy_database <new_database_name>")
    target = sys.argv[1]
    source = settings.mongodb_db
    if target == source:
        sys.exit("The copy needs a different name from the original database.")
    client = MongoClient(settings.mongodb_uri)
    src, dst = client[source], client[target]
    if dst.list_collection_names() and input(f"'{target}' already has data. Replace it? (y/n) ").lower() != "y":
        sys.exit("Cancelled.")
    for name in src.list_collection_names():
        dst[name].drop()
        docs = list(src[name].find())
        if docs:
            dst[name].insert_many(docs)
        for idx in src[name].list_indexes():
            if idx["name"] != "_id_":
                keys = list(idx["key"].items())
                opts = {k: v for k, v in idx.items() if k in ("unique", "sparse", "expireAfterSeconds", "name")}
                dst[name].create_index(keys, **opts)
        print(f"  {name}: {len(docs)} records")
    print(f"Done. '{source}' copied to '{target}'.")


if __name__ == "__main__":
    main()
