from fastapi import FastAPI

app = FastAPI(title="OneStopShop API")


@app.get("/")
def read_root() -> dict[str, str]:
    return {"message": "OneStopShop backend is running"}
