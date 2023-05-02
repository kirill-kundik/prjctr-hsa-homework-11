import os
import uuid
import warnings

from elasticsearch import AsyncElasticsearch
from faker import Faker
from fastapi import FastAPI
from pydantic import BaseModel

warnings.filterwarnings("ignore")

es = AsyncElasticsearch(f"http://{os.environ['ELASTIC_HOST']}:{os.environ['ELASTIC_PORT']}")

app = FastAPI()

fake = Faker()

FUZZINESS_LEVEL = 3
INDEX_NAME = "my_index"
INDEX_SETTINGS = {
    "settings": {
        "analysis": {
            "analyzer": {
                "autocomplete": {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": [
                        "lowercase",
                        "autocomplete_filter"
                    ]
                }
            },
            "filter": {
                "autocomplete_filter": {
                    "type": "edge_ngram",
                    "min_gram": 3,
                    "max_gram": 15
                }
            }
        }
    },
    "mappings": {
        "properties": {
            "description": {
                "type": "text",
                "analyzer": "autocomplete",
                "search_analyzer": "standard"
            },
            "name": {
                "type": "text",
                "analyzer": "autocomplete",
                "search_analyzer": "standard"
            }
        }
    }
}
INITIAL_NB_OF_DOCS = 10
MAX_HITS_LIMIT = 3
MIN_QUERY_LENGTH = 7


def build_search_query(q, fuzziness=None):
    query = {
        "query": {
            "multi_match": {
                "query": q,
                "fields": ["name", "description"]
            }
        }
    }

    if fuzziness:
        query["query"]["multi_match"]["fuzziness"] = str(fuzziness)

    return query


class Item(BaseModel):
    name: str
    description: str


@app.on_event("startup")
async def startup():
    index_exists = await es.indices.exists(index=INDEX_NAME)

    if not index_exists:
        await es.indices.create(index=INDEX_NAME, body=INDEX_SETTINGS)

        for _ in range(INITIAL_NB_OF_DOCS):
            await es.create(
                index=INDEX_NAME, id=str(uuid.uuid4()),
                document={"name": fake.sentence(), "description": fake.text(max_nb_chars=2000), },
            )


@app.on_event("shutdown")
async def shutdown():
    await es.close()


@app.post("/insert")
async def insert(item: Item):
    await es.create(
        index=INDEX_NAME, id=str(uuid.uuid4()),
        document={"name": item.name, "description": item.description, },
    )

    return {"success": True}


@app.get("/insert_random")
async def insert_random():
    await es.create(
        index=INDEX_NAME, id=str(uuid.uuid4()),
        document={"name": fake.sentence(), "description": fake.text(max_nb_chars=2000), },
    )

    return {"success": True}


@app.get("/search")
async def search(q: str):
    if not q:
        return {"error": "Please enter your search query in the 'q' URL query parameter."}

    body = build_search_query(
        q.lower(), fuzziness=FUZZINESS_LEVEL if len(q) > MIN_QUERY_LENGTH else None
    )

    res = await es.search(index=INDEX_NAME, body=body)

    if res["hits"]["hits"]:
        res = [
            Item(name=hit["_source"]["name"], description=hit["_source"]["description"])
            for hit in res["hits"]["hits"][:MAX_HITS_LIMIT]
        ]

    else:
        res = []

    return res
