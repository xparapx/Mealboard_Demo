from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from .config import BASE
from .routers import status, history, meal

app = FastAPI(title="Mealboard")
app.include_router(status.router)
app.include_router(history.router)
app.include_router(meal.router)
# 정적 파일은 마지막에 mount — /api/* 가 먼저 잡히도록
app.mount("/", StaticFiles(directory=BASE / "static", html=True), name="static")
