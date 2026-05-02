"""
HTTP API for the local TIMER3 Spearman lookup.

Run:
    uv run uvicorn reproduce.server:app --reload --port 8080

Endpoints:
    GET  /                  -> service metadata
    GET  /genes             -> list of available genes (large)
    GET  /cancers           -> 36 cancer labels + sample counts
    GET  /features          -> 119 immune-feature column names
    GET  /gene/{symbol}     -> long-form correlations across all cancers/features
                               query params: cancer=..., feature_substr=...,
                                             top=N (rank by |rho|), format=long|wide
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

from .api import LocalTimer3

app = FastAPI(
    title="timer3-agent local API",
    description="Offline replica of TIMER3 Immune_Gene Spearman correlations.",
    version="0.1.0",
)


@lru_cache(maxsize=1)
def _api() -> LocalTimer3:
    return LocalTimer3()


@app.get("/")
def root():
    a = _api()
    return {
        "name": "timer3-agent local API",
        "n_genes": len(a.genes),
        "n_cancers": len(a.cancers),
        "n_features": len(a.features),
        "endpoints": ["/genes", "/cancers", "/features", "/gene/{symbol}"],
    }


@app.get("/genes")
def list_genes(prefix: str | None = None, limit: int = 100):
    g = _api().genes
    if prefix:
        p = prefix.upper()
        g = [x for x in g if x.upper().startswith(p)]
    return {"count": len(g), "genes": g[:limit]}


@app.get("/cancers")
def list_cancers():
    a = _api()
    return [{"cancer": c, "n": int(n)} for c, n in zip(a.cancers, a._n)]


@app.get("/features")
def list_features():
    a = _api()
    return {"count": len(a.features), "features": a.features}


@app.get("/gene/{symbol}")
def gene(
    symbol: str,
    cancer: str | None = Query(None, description="Filter to one cancer label"),
    feature_substr: str | None = Query(None, description="Substring filter on feature name"),
    top: int | None = Query(None, ge=1, description="Return only top-N rows by |rho|"),
    format: str = Query("long", pattern="^(long|wide)$"),
):
    a = _api()
    try:
        df = a.gene(symbol, cancer=cancer, feature_substr=feature_substr)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))

    df = df.dropna(subset=["rho"])
    df["rho"] = df["rho"].round(4)
    if top is not None:
        df = df.reindex(df["rho"].abs().sort_values(ascending=False).index).head(top)

    if format == "wide":
        wide = df.pivot(index="cancer", columns="feature", values="rho").reset_index()
        return JSONResponse(content=wide.to_dict(orient="records"))
    return JSONResponse(content=df.to_dict(orient="records"))
