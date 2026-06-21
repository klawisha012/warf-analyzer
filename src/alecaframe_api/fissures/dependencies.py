"""DI singleton for the fissures router, populated by main.py lifespan."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from alecaframe_api.fissures.client import FissureClient

fissure_client: FissureClient | None = None


def get_fissure_client() -> FissureClient:
    if fissure_client is None:
        raise RuntimeError("FissureClient not initialised; main.py lifespan must set it")
    return fissure_client


FissureClientDep = Annotated[FissureClient, Depends(get_fissure_client)]
