"""FastAPI dependency providers for the WFM submodule.

We don't import these from main.py's lifespan directly — main.py creates the
real objects in lifespan and stores them on module-level singletons in
`alecaframe_api.wfm.dependencies` (similar to how `bridge` and `resolver`
already live as globals in `main.py`).

This keeps the wfm/router.py clean: it just declares `Depends(get_wfm_client)`
and gets back the singleton.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from alecaframe_api.db.repo import Repo
from alecaframe_api.wfm.client import WFMClient
from alecaframe_api.wfm.sets import SetIndex
from alecaframe_api.wfm.slugs import SlugResolver


# Singletons populated by main.py lifespan.
wfm_client: WFMClient | None = None
slug_resolver: SlugResolver | None = None
set_index: SetIndex | None = None
repo: Repo | None = None


def get_wfm_client() -> WFMClient:
    if wfm_client is None:
        raise RuntimeError("WFMClient not initialised; main.py lifespan must set it")
    return wfm_client


def get_slug_resolver() -> SlugResolver:
    if slug_resolver is None:
        raise RuntimeError("SlugResolver not initialised")
    return slug_resolver


def get_set_index() -> SetIndex:
    if set_index is None:
        raise RuntimeError("SetIndex not initialised")
    return set_index


def get_repo() -> Repo:
    if repo is None:
        raise RuntimeError("Repo not initialised; main.py lifespan must set it")
    return repo


WFMClientDep = Annotated[WFMClient, Depends(get_wfm_client)]
SlugResolverDep = Annotated[SlugResolver, Depends(get_slug_resolver)]
SetIndexDep = Annotated[SetIndex, Depends(get_set_index)]
RepoDep = Annotated[Repo, Depends(get_repo)]
