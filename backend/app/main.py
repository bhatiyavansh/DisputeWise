from fastapi import FastAPI

from app.api import cases, decisions, drafts, evidence, scoring

app = FastAPI(
    title="DisputeWise API",
    description="AI-powered chargeback intelligence — defense-only decision support.",
    version="0.1.0",
)

app.include_router(cases.router)
app.include_router(evidence.router)
app.include_router(scoring.router)
app.include_router(decisions.router)
app.include_router(drafts.router)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
