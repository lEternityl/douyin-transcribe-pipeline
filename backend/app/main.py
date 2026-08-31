"""FastAPI 应用入口。"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import cookie, files, tasks, users
from app.config import settings
from app.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动:建表(开发期;生产用 alembic upgrade head)
    init_db()
    yield


app = FastAPI(
    title="抖音下载/转写流水线 API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users.router)
app.include_router(cookie.router)
app.include_router(tasks.router)
app.include_router(files.router)


@app.get("/")
def root() -> dict:
    return {"name": "douyin-web-backend", "docs": "/docs"}
