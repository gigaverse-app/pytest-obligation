"""Real MongoDB resources shared by integration proofs."""

import os
from uuid import uuid4

import pytest
from pymongo import MongoClient


@pytest.fixture
def client():
    with MongoClient(
        os.environ.get("MONGODB_URI", "mongodb://localhost:27028/?directConnection=true"), retryWrites=False
    ) as client:
        client.admin.command("ping")
        yield client


@pytest.fixture
def collection(client):
    collection = client[f"due_work_{uuid4().hex}"].work
    yield collection
    client.drop_database(collection.database.name)
