"""YouTube publish stubs for Ops Center (auth placeholder + draft upload)."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_api.auth import Authenticated
from titan_api.deps import db_session
from titan_api.youtube_stub import (
    account_json,
    approve_upload,
    connect_stub_account,
    create_draft_upload,
    disconnect_stub_account,
    get_youtube_account,
    list_upload_jobs,
    run_stub_upload,
    upload_json,
)
from titan_core.errors import ErrorCode, TitanError
from titan_db.models.publishing import VideoProject

router = APIRouter(tags=["publish"], dependencies=[Authenticated])
SessionDep = Depends(db_session)


class DraftUploadBody(BaseModel):
    title: str = Field(default="Titan session draft", min_length=1, max_length=200)
    session_id: UUID | None = None
    privacy: Literal["private", "unlisted", "public"] = "private"


@router.get("/accounts/youtube")
async def youtube_account_status(db: AsyncSession = SessionDep) -> dict[str, Any]:
    row = await get_youtube_account(db)
    if row is None:
        return {
            "connected": False,
            "stub": True,
            "account": None,
            "message": "No YouTube account linked. Connect stub auth for beta draft uploads.",
        }
    return {
        "connected": row.status == "connected",
        "stub": True,
        "account": account_json(row),
        "message": (
            "Stub account connected — real Google OAuth arrives in Phase 7."
            if row.status == "connected"
            else "Stub account revoked."
        ),
    }


@router.post("/accounts/youtube/connect")
async def youtube_connect_stub(db: AsyncSession = SessionDep) -> dict[str, Any]:
    row = await connect_stub_account(db)
    return {
        "connected": True,
        "stub": True,
        "account": account_json(row),
        "message": "YouTube stub auth connected (credential placeholder; no Google call).",
    }


@router.post("/accounts/youtube/disconnect")
async def youtube_disconnect_stub(db: AsyncSession = SessionDep) -> dict[str, Any]:
    row = await disconnect_stub_account(db)
    if row is None:
        return {
            "connected": False,
            "stub": True,
            "account": None,
            "message": "No stub account to disconnect.",
        }
    return {
        "connected": False,
        "stub": True,
        "account": account_json(row),
        "message": "YouTube stub auth disconnected.",
    }


@router.get("/upload-jobs")
async def get_upload_jobs(limit: int = 20, db: AsyncSession = SessionDep) -> dict[str, Any]:
    rows = await list_upload_jobs(db, limit=limit)
    return {"items": [upload_json(job, project=project) for job, project in rows]}


@router.post("/upload-jobs", status_code=201)
async def post_upload_job(body: DraftUploadBody, db: AsyncSession = SessionDep) -> dict[str, Any]:
    job, project = await create_draft_upload(
        db,
        title=body.title,
        session_id=body.session_id,
        privacy=body.privacy,
    )
    return upload_json(job, project=project)


@router.post("/upload-jobs/{job_id}/approve")
async def post_approve_upload(job_id: UUID, db: AsyncSession = SessionDep) -> dict[str, Any]:
    job = await approve_upload(db, job_id)
    project = await db.scalar(select(VideoProject).where(VideoProject.id == job.video_project_id))
    if project is None:
        raise TitanError(ErrorCode.NOT_FOUND, "video project missing for upload job")
    return upload_json(job, project=project)


@router.post("/upload-jobs/{job_id}/upload")
async def post_stub_upload(job_id: UUID, db: AsyncSession = SessionDep) -> dict[str, Any]:
    job = await run_stub_upload(db, job_id)
    project = await db.scalar(select(VideoProject).where(VideoProject.id == job.video_project_id))
    if project is None:
        raise TitanError(ErrorCode.NOT_FOUND, "video project missing for upload job")
    return upload_json(job, project=project)
