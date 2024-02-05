import os

from dotenv import find_dotenv, load_dotenv
from fastapi import FastAPI, HTTPException
from langchain.schema import Document
from langchain_openai import OpenAIEmbeddings

from models import DocumentModel, DocumentResponse
from store import ExecutorPgVector, FullyAsyncPgVector
from store_factory import get_vector_store

load_dotenv(find_dotenv())

app = FastAPI()


def get_env_variable(var_name: str) -> str:
    value = os.getenv(var_name)
    if value is None:
        raise ValueError(f"Environment variable '{var_name}' not found.")
    return value


try:
    USE_ASYNC = os.getenv("USE_ASYNC", "False").lower() == "true"
    if USE_ASYNC:
        print("Async project used")

    POSTGRES_DB = get_env_variable("POSTGRES_DB")
    POSTGRES_USER = get_env_variable("POSTGRES_USER")
    POSTGRES_PASSWORD = get_env_variable("POSTGRES_PASSWORD")
    DB_HOST = get_env_variable("DB_HOST")
    DB_PORT = get_env_variable("DB_PORT")

    SYNC_CONNECTION_STRING = f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{DB_HOST}:{DB_PORT}/{POSTGRES_DB}"
    ASYNC_CONNECTION_STRING = f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{DB_HOST}:{DB_PORT}/{POSTGRES_DB}"

    OPENAI_API_KEY = get_env_variable("OPENAI_API_KEY")
    embeddings = OpenAIEmbeddings()

    mode = "async" if USE_ASYNC else "sync"
    pgvector_store = get_vector_store(
        SYNC_CONNECTION_STRING, ASYNC_CONNECTION_STRING, embeddings, mode
    )
    retriever = pgvector_store.as_retriever()
except ValueError as e:
    raise HTTPException(status_code=500, detail=str(e))
except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))


@app.post("/add-documents/")
async def add_documents(documents: list[DocumentModel]):
    try:
        docs = [
            Document(
                page_content=doc.page_content,
                metadata=(
                    {**doc.metadata, "digest": doc.generate_digest()}
                    if doc.metadata
                    else {"digest": doc.generate_digest()}
                ),
            )
            for doc in documents
        ]
        ids = (
            await pgvector_store.add_documents(docs)
            if isinstance(pgvector_store, (ExecutorPgVector, FullyAsyncPgVector))
            else pgvector_store.add_documents(docs)
        )
        return {"message": "Documents added successfully", "ids": ids}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/get-all-ids/")
async def get_all_ids():
    try:
        if isinstance(pgvector_store, (ExecutorPgVector, FullyAsyncPgVector)):
            ids = await pgvector_store.get_all_ids()
        else:  # Sync operation for ExtendedPgVector
            ids = pgvector_store.get_all_ids()

        return ids
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/chat/")
async def quick_response():
    pass  # to be implemented


@app.post("/get-documents-by-ids/", response_model=list[DocumentResponse])
async def get_documents_by_ids(ids: list[str]):
    try:
        if isinstance(pgvector_store, (ExecutorPgVector, FullyAsyncPgVector)):
            existing_ids = await pgvector_store.get_all_ids()
            documents = await pgvector_store.get_documents_by_ids(ids)
        else:  # Sync operation for ExtendedPgVector
            existing_ids = pgvector_store.get_all_ids()
            documents = pgvector_store.get_documents_by_ids(ids)

        if not all(id in existing_ids for id in ids):
            raise HTTPException(status_code=404, detail="One or more IDs not found")

        return documents
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/delete-documents/")
async def delete_documents(ids: list[str]):
    try:
        if isinstance(pgvector_store, (ExecutorPgVector, FullyAsyncPgVector)):
            existing_ids = await pgvector_store.get_all_ids()
            await pgvector_store.delete(ids=ids)
        else:  # Sync operation for ExtendedPgVector
            existing_ids = pgvector_store.get_all_ids()
            pgvector_store.delete(ids=ids)

        if not all(id in existing_ids for id in ids):
            raise HTTPException(status_code=404, detail="One or more IDs not found")

        return {"message": f"{len(ids)} documents deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))