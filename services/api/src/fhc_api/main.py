from fastapi import FastAPI

from fhc_api import __doc__ as description


def create_app() -> FastAPI:
    app = FastAPI(title="FHC Admin API", description=description or "")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "api"}

    return app


app = create_app()
