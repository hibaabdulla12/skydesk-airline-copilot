from fastapi import FastAPI

app = FastAPI(title="SkyDesk")

@app.get("/health")
def health():
    return {"status": "ok"}