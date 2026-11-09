"""YouTube auth + draft upload stubs (beta). No Google OAuth or resumable upload yet."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_core.clock import utc_now
from titan_core.errors import ErrorCode, TitanError
from titan_core.ids import uuid7
from titan_db.models.publishing import PlatformAccount, UploadJob, VideoProject
from titan_db.models.recording import Recording
from titan_db.models.sessions import Session

STUB_CHANNEL_ID = "stub-channel"
STUB_CREDENTIAL_REF = "titan/youtube/stub"
STUB_DISPLAY_NAME = "YouTube (stub)"
PLATFORM = "youtube"


def account_json(row: PlatformAccount) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "platform": row.platform,
        "display_name": row.display_name,
        "remote_channel_id": row.remote_channel_id,
        "credential_ref": row.credential_ref,
        "status": row.status,
        "scopes": list(row.scopes or []),
        "connected_at": row.connected_at.isoformat() if row.connected_at else None,
        "stub": row.credential_ref == STUB_CREDENTIAL_REF or row.remote_channel_id == STUB_CHANNEL_ID,
    }


def upload_json(row: UploadJob, *, project: VideoProject | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": str(row.id),
        "video_project_id": str(row.video_project_id),
        "account_id": str(row.account_id),
        "platform": row.platform,
        "status": row.status,
        "privacy": row.privacy,
        "metadata": row.upload_metadata or {},
        "approved_at": row.approved_at.isoformat() if row.approved_at else None,
        "approved_by": row.approved_by,
        "remote_video_id": row.remote_video_id,
        "remote_url": row.remote_url,
        "bytes_sent": row.bytes_sent,
        "bytes_total": row.bytes_total,
        "last_error": row.last_error,
        "attempts": row.attempts,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
    if project is not None:
        payload["title"] = project.title
        payload["session_id"] = str(project.session_id) if project.session_id else None
    return payload


async def get_youtube_account(db: AsyncSession) -> PlatformAccount | None:
    return await db.scalar(
        select(PlatformAccount)
        .where(PlatformAccount.platform == PLATFORM)
        .where(PlatformAccount.remote_channel_id == STUB_CHANNEL_ID)
        .limit(1)
    )


async def connect_stub_account(db: AsyncSession) -> PlatformAccount:
    existing = await get_youtube_account(db)
    if existing is not None:
        existing.status = "connected"
        existing.display_name = STUB_DISPLAY_NAME
        existing.credential_ref = STUB_CREDENTIAL_REF
        existing.scopes = ["youtube.upload", "youtube.readonly"]
        existing.connected_at = utc_now()
        await db.flush()
        return existing
    row = PlatformAccount(
        id=uuid7(),
        platform=PLATFORM,
        display_name=STUB_DISPLAY_NAME,
        remote_channel_id=STUB_CHANNEL_ID,
        scopes=["youtube.upload", "youtube.readonly"],
        credential_ref=STUB_CREDENTIAL_REF,
        status="connected",
        connected_at=utc_now(),
    )
    db.add(row)
    await db.flush()
    return row


async def disconnect_stub_account(db: AsyncSession) -> PlatformAccount | None:
    existing = await get_youtube_account(db)
    if existing is None:
        return None
    # Schema allows connected|expired|revoked (no "disconnected").
    existing.status = "revoked"
    await db.flush()
    return existing


async def create_draft_upload(
    db: AsyncSession,
    *,
    title: str,
    session_id: UUID | None,
    privacy: str = "private",
) -> tuple[UploadJob, VideoProject]:
    account = await get_youtube_account(db)
    if account is None or account.status != "connected":
        raise TitanError(
            ErrorCode.INVALID_STATE_TRANSITION,
            "Connect the YouTube stub account before creating a draft upload",
        )
    session_row: Session | None = None
    if session_id is not None:
        session_row = await db.scalar(select(Session).where(Session.id == session_id))
        if session_row is None:
            raise TitanError(ErrorCode.NOT_FOUND, f"session {session_id} not found")
    recording = None
    if session_id is not None:
        recording = await db.scalar(
            select(Recording)
            .where(Recording.session_id == session_id)
            .order_by(Recording.created_at.desc())
            .limit(1)
        )
    project = VideoProject(
        id=uuid7(),
        session_id=session_id,
        title=title.strip() or "Untitled Titan draft",
        status="draft",
        seo={
            "stub": True,
            "description": "Draft created by Titan YouTube upload stub (no Google API call).",
            "tags": ["titan", "stub", "gaming"],
        },
        chapters=[],
        render_profile={"stub": True},
        output_path=recording.root_dir if recording is not None else None,
    )
    db.add(project)
    await db.flush()
    job = UploadJob(
        id=uuid7(),
        video_project_id=project.id,
        account_id=account.id,
        platform=PLATFORM,
        status="awaiting_approval",
        privacy=privacy if privacy in {"private", "unlisted", "public"} else "private",
        upload_metadata={
            "stub": True,
            "title": project.title,
            "source_recording_id": str(recording.id) if recording is not None else None,
            "message": "Private-first draft; approve in Ops Center, then run stub upload.",
        },
        bytes_sent=0,
        bytes_total=None,
        attempts=0,
        quota_units_used=0,
    )
    db.add(job)
    await db.flush()
    return job, project


async def list_upload_jobs(db: AsyncSession, *, limit: int = 20) -> list[tuple[UploadJob, VideoProject]]:
    capped = max(1, min(limit, 100))
    rows = (
        await db.execute(
            select(UploadJob, VideoProject)
            .join(VideoProject, VideoProject.id == UploadJob.video_project_id)
            .where(UploadJob.platform == PLATFORM)
            .order_by(UploadJob.created_at.desc())
            .limit(capped)
        )
    ).all()
    return [(job, project) for job, project in rows]


async def approve_upload(db: AsyncSession, job_id: UUID, *, approved_by: str = "user") -> UploadJob:
    job = await db.scalar(select(UploadJob).where(UploadJob.id == job_id))
    if job is None:
        raise TitanError(ErrorCode.NOT_FOUND, f"upload job {job_id} not found")
    if job.status not in {"draft", "awaiting_approval"}:
        raise TitanError(
            ErrorCode.INVALID_STATE_TRANSITION,
            f"cannot approve upload in status={job.status!r}",
        )
    job.status = "approved"
    job.approved_at = utc_now()
    job.approved_by = approved_by
    await db.flush()
    return job


async def run_stub_upload(db: AsyncSession, job_id: UUID) -> UploadJob:
    job = await db.scalar(select(UploadJob).where(UploadJob.id == job_id))
    if job is None:
        raise TitanError(ErrorCode.NOT_FOUND, f"upload job {job_id} not found")
    if job.status != "approved" or job.approved_at is None:
        raise TitanError(
            ErrorCode.INVALID_STATE_TRANSITION,
            "approve the draft upload before running the stub uploader",
        )
    job.status = "uploading"
    job.attempts = int(job.attempts or 0) + 1
    await db.flush()
    fake_id = f"stub-{str(job.id).replace('-', '')[:11]}"
    job.status = "published"
    job.remote_video_id = fake_id
    job.remote_url = f"https://studio.youtube.com/video/{fake_id}/edit"
    job.bytes_sent = job.bytes_total or 0
    job.last_error = None
    job.quota_units_used = int(job.quota_units_used or 0) + 1600
    project = await db.scalar(select(VideoProject).where(VideoProject.id == job.video_project_id))
    if project is not None:
        project.status = "published"
    await db.flush()
    return job
