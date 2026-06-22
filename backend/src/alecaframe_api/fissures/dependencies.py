"""DI singleton for the fissures router, populated by main.py lifespan."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from alecaframe_api.fissures.client import FissureClient
from alecaframe_api.reference.nodes_loader import NodeCatalog

fissure_client: FissureClient | None = None
node_catalog: NodeCatalog | None = None


def get_fissure_client() -> FissureClient:
    if fissure_client is None:
        raise RuntimeError(
            "FissureClient not initialised; main.py lifespan must set it"
        )
    return fissure_client


def get_node_catalog() -> NodeCatalog:
    if node_catalog is None:
        raise RuntimeError("NodeCatalog not initialised; main.py lifespan must set it")
    return node_catalog


FissureClientDep = Annotated[FissureClient, Depends(get_fissure_client)]
NodeCatalogDep = Annotated[NodeCatalog, Depends(get_node_catalog)]
