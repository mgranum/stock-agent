from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.api.models import (
    AdminStateResponse,
    ChatRequest,
    ChatResponse,
    CompanyDetailResponse,
    ExploreResponse,
    HealthResponse,
    ModelStatusResponse,
    PositionsResponse,
    RefreshStatusResponse,
    SearchResponse,
    TodayResponse,
    RollbackResponse,
    StockMutationRequest,
    StockMutationResponse,
    WatchlistsResponse,
)
from src.admin_service import AdminMutationService, AdminWritesDisabled
from src.company_detail_query import CompanyDetailQuery, PERIODS
from src.environment import get_environment
from src.presentation_queries import PresentationQueries


def create_app(
    query: CompanyDetailQuery | None = None,
    presentation_queries: PresentationQueries | None = None,
    admin_service: AdminMutationService | None = None,
) -> FastAPI:
    company_query = query or CompanyDetailQuery()
    presentation = presentation_queries or PresentationQueries()
    admin = admin_service or AdminMutationService()
    app = FastAPI(
        title="Stock Agent API",
        version="0.2.0",
        description="Typet API for den trinnvise frontendmigrasjonen.",
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
            detail = company_query.get(ticker, period)
            context = presentation.company_context(detail.ticker)
            return {
                **asdict(detail),
                **context,
            }
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail=f"Kunne ikke hente selskapsdata for {ticker.upper()}",
            ) from exc

    @app.get("/api/today", response_model=TodayResponse)
    def today():
        return presentation.today()

    @app.get("/api/explore", response_model=ExploreResponse)
    def explore():
        return presentation.explore()

    @app.get("/api/positions", response_model=PositionsResponse)
    def positions():
        return presentation.positions()

    @app.get("/api/watchlists", response_model=WatchlistsResponse)
    def watchlists():
        return presentation.watchlists()

    @app.get("/api/search", response_model=SearchResponse)
    def search(
        q: str = Query(min_length=1, max_length=100),
        limit: int = Query(default=20, ge=1, le=50),
    ):
        return presentation.search(q, limit=limit)

    @app.get("/api/model-status", response_model=ModelStatusResponse)
    def model_status():
        return presentation.model_status()

    @app.get("/api/refresh/status", response_model=RefreshStatusResponse)
    def refresh_status():
        return presentation.refresh_status()

    @app.post("/api/chat", response_model=ChatResponse)
    def chat(request: ChatRequest):
        try:
            return presentation.chat(request.question.strip())
        except LookupError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/api/admin", response_model=AdminStateResponse)
    def admin_state():
        positions = presentation.positions()
        watchlists = presentation.watchlists()
        return {
            "meta": positions["meta"],
            "writable": get_environment() == "test",
            "positions": positions["positions"],
            "watchlists": watchlists["watchlists"],
        }

    @app.put("/api/admin/stocks/{ticker}", response_model=StockMutationResponse)
    def update_stock(ticker: str, request: StockMutationRequest):
        if request.owned and request.average_cost is None:
            raise HTTPException(
                status_code=422,
                detail="GAV må oppgis for en eid aksje.",
            )
        try:
            return admin.update_stock(
                ticker,
                owned=request.owned,
                average_cost=request.average_cost,
                watchlists=request.watchlists,
            )
        except AdminWritesDisabled as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post(
        "/api/admin/rollback/{backup_id}",
        response_model=RollbackResponse,
    )
    def rollback(backup_id: str):
        try:
            return admin.rollback(backup_id)
        except AdminWritesDisabled as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

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
