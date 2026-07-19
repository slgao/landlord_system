"""Embedding backends behind one interface, so the rest of the pipeline
doesn't care whether embeddings come from a local model or Bedrock.

`intfloat/multilingual-e5-base` is the local default: it's one of the few
open embedding models trained with strong German coverage, and — this is
the detail worth knowing cold — e5 models require a `"query: "` /
`"passage: "` prefix on the input text. Skipping the prefix silently
degrades retrieval quality instead of erroring, which makes it an easy bug
to ship without noticing.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from functools import lru_cache


class Embedder(ABC):
    dimension: int

    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    @abstractmethod
    def embed_query(self, text: str) -> list[float]: ...


class LocalEmbedder(Embedder):
    """sentence-transformers, runs on CPU, no API cost, no network."""

    dimension = 768

    def __init__(self, model_name: str = "intfloat/multilingual-e5-base"):
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        prefixed = [f"passage: {t}" for t in texts]
        return self._model.encode(prefixed, normalize_embeddings=True).tolist()

    def embed_query(self, text: str) -> list[float]:
        return self._model.encode(f"query: {text}", normalize_embeddings=True).tolist()


class BedrockEmbedder(Embedder):
    """Amazon Titan Text Embeddings V2, via bedrock-runtime InvokeModel.

    Same interface as LocalEmbedder — swapping this in is a one-line change
    in pipeline.py. Titan V2 has no query/passage prefix convention (unlike
    e5); it also supports a `dimensions` param (256/512/1024) to trade
    recall for storage/latency, which is a cheap production lever.
    """

    dimension = 1024

    def __init__(self, model_id: str = "amazon.titan-embed-text-v2:0", region: str = "eu-central-1"):
        import boto3

        self._client = boto3.client("bedrock-runtime", region_name=region)
        self._model_id = model_id

    def _invoke(self, text: str) -> list[float]:
        body = json.dumps({"inputText": text, "dimensions": self.dimension, "normalize": True})
        resp = self._client.invoke_model(modelId=self._model_id, body=body)
        return json.loads(resp["body"].read())["embedding"]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        # Titan has no batch endpoint in the base InvokeModel API — sequential
        # calls here. At real scale you'd parallelize with a thread pool and
        # respect the account's Bedrock TPS quota, same shape of problem as
        # the Groq TPD routing in the auto-apply-bot project.
        return [self._invoke(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._invoke(text)


@lru_cache(maxsize=1)
def get_default_embedder() -> Embedder:
    return LocalEmbedder()
