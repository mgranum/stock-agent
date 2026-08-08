from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.api.models import CompanyDetailResponse, HealthResponse
from src.company_detail_query import CompanyDetailQuery, PERIODS
from src.environment import get_environment


def create_app(query: CompanyDetailQuery | None = None) -> FastAPI:
    company_query = query or CompanyDetailQuery()
    app = FastAPI(
        title="Stock Agent API",
        version="0.1.0",
        description="Skrivebeskyttet API for migrasjonsspieken.",
    )

    @app.get("/api/health", response_model=HealthResponse)
    def health():
        return HealthResponse(status="ok", environment=get_environment())

    @app.get("/api/stocks/{ticker}", response_model=CompanyDetailResponse)
    def company_detail(
        ticker: str,
        period: str = Query(default="3m", description=f"En av: {', '.join(PERIODS)}"),
    ):
        try:
            return company_query.get(ticker, period)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail=f"Kunne ikke hente selskapsdata for {ticker.upper()}",
            ) from exc

    frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    assets_dir = frontend_dist / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        index_file = frontend_dist / "index.html"
        if not index_file.exists():
            raise HTTPException(
                status_code=404,
                detail="Frontend er ikke bygget. Kjør npm run build i frontend/.",
            )
        return FileResponse(index_file)

    return app


app = create_app()
