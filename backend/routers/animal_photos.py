"""Animal photos stored in Google Cloud Storage."""
import logging
import os
import uuid
from datetime import date, timedelta
from typing import List, Optional

from auth import require_roles
from database import get_db
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from models import AnimalPhoto, User, UserRole
from pydantic import ValidationError
from schemas import AnimalPhotoCreate, AnimalPhotoResponse, AnimalPhotoUpdate
from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from services.common import _ANY_ROLE, _require_animal

logger = logging.getLogger(__name__)
router = APIRouter()

ALLOWED_PHOTO_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
MAX_PHOTO_BYTES = 10 * 1024 * 1024


class _GCSUnavailable(Exception):
    """GCS_BUCKET_NAME unset or google-cloud-storage not installed."""



# ---------- Animal photos (Google Cloud Storage) ----------
def _gcs_bucket():
    """Sync (run in a thread). google.cloud.storage is imported lazily on purpose."""
    bucket_name = os.environ.get("GCS_BUCKET_NAME")
    if not bucket_name:
        raise _GCSUnavailable("GCS_BUCKET_NAME is not set")
    try:
        from google.cloud import storage
    except ImportError as exc:
        raise _GCSUnavailable("google-cloud-storage is not installed") from exc
    return storage.Client().bucket(bucket_name)


def _gcs_upload(path: str, data: bytes, content_type: str) -> None:
    _gcs_bucket().blob(path).upload_from_string(data, content_type=content_type)


def _gcs_delete(path: str) -> None:
    bucket = _gcs_bucket()
    from google.api_core.exceptions import NotFound
    try:
        bucket.blob(path).delete()
    except NotFound:
        pass  # already gone: the DB row can still be removed


def _gcs_sign_urls(paths: List[str]) -> dict:
    """1-hour v4 signed GET URLs. Falls back to IAM signing when the credentials have no private key."""
    bucket = _gcs_bucket()
    expiry = timedelta(hours=1)
    iam_args = None
    urls = {}
    for path in paths:
        blob = bucket.blob(path)
        try:
            urls[path] = blob.generate_signed_url(version="v4", expiration=expiry, method="GET")
        except Exception:
            if iam_args is None:
                import google.auth
                from google.auth.transport.requests import Request
                creds, _ = google.auth.default()
                creds.refresh(Request())
                iam_args = {"service_account_email": creds.service_account_email, "access_token": creds.token}
            urls[path] = blob.generate_signed_url(version="v4", expiration=expiry, method="GET", **iam_args)
    return urls


def _sniff_image_ext(data: bytes) -> Optional[str]:
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


async def _photo_responses(photos: List[AnimalPhoto]) -> List[AnimalPhotoResponse]:
    responses = [AnimalPhotoResponse.model_validate(p) for p in photos]
    if not responses:
        return responses
    if not os.environ.get("GCS_BUCKET_NAME"):
        for r in responses:
            r.warning = "GCS_BUCKET_NAME is not set; photo URLs are unavailable"
        return responses
    try:
        urls = await run_in_threadpool(_gcs_sign_urls, [p.gcs_path for p in photos])
    except Exception as exc:
        logger.warning("Photo URL signing failed: %s", type(exc).__name__)
        for r in responses:
            r.warning = "Could not generate photo URLs"
        return responses
    for r in responses:
        r.photo_url = urls.get(r.gcs_path)
    return responses


async def _load_photo(db: AsyncSession, animal_id: int, photo_id: int) -> AnimalPhoto:
    result = await db.execute(
        select(AnimalPhoto).where(and_(AnimalPhoto.id == photo_id, AnimalPhoto.animal_id == animal_id))
    )
    photo = result.scalar_one_or_none()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    return photo


@router.get("/animals/{animal_id}/photos", response_model=List[AnimalPhotoResponse])
async def list_animal_photos(
    animal_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(*_ANY_ROLE)),
):
    await _require_animal(db, animal_id)
    result = await db.execute(
        select(AnimalPhoto).where(AnimalPhoto.animal_id == animal_id)
        .order_by(AnimalPhoto.is_primary.desc(), AnimalPhoto.uploaded_at.desc(), AnimalPhoto.id.desc())
    )
    return await _photo_responses(result.scalars().all())


@router.post("/animals/{animal_id}/photos", response_model=AnimalPhotoResponse)
async def upload_animal_photo(
    animal_id: int,
    file: UploadFile = File(...),
    caption: Optional[str] = Form(None),
    taken_date: Optional[date] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY)),
):
    await _require_animal(db, animal_id)
    if not os.environ.get("GCS_BUCKET_NAME"):
        raise HTTPException(status_code=503, detail="Photo storage is not configured")
    content_type = (file.content_type or "").lower()
    declared_ext = ALLOWED_PHOTO_TYPES.get(content_type)
    if declared_ext is None:
        raise HTTPException(status_code=415, detail="Only image/jpeg, image/png and image/webp are accepted")
    data = await file.read(MAX_PHOTO_BYTES + 1)
    if len(data) > MAX_PHOTO_BYTES:
        raise HTTPException(status_code=413, detail="Photo exceeds the 10 MB limit")
    ext = _sniff_image_ext(data)
    if ext is None or ext != declared_ext:
        raise HTTPException(status_code=415, detail="File content does not match an allowed image type")
    try:
        meta = AnimalPhotoCreate(caption=caption, taken_date=taken_date)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors(include_url=False, include_context=False))

    path = f"animals/{animal_id}/{uuid.uuid4()}.{ext}"
    try:
        await run_in_threadpool(_gcs_upload, path, data, content_type)
    except _GCSUnavailable as exc:
        raise HTTPException(status_code=503, detail=f"Photo storage is unavailable: {exc}")
    except Exception as exc:
        logger.warning("Photo upload failed: %s", type(exc).__name__)
        raise HTTPException(status_code=502, detail="Photo upload to storage failed")

    existing = (await db.execute(
        select(func.count(AnimalPhoto.id)).where(AnimalPhoto.animal_id == animal_id)
    )).scalar()
    photo = AnimalPhoto(
        animal_id=animal_id, gcs_path=path, caption=meta.caption, taken_date=meta.taken_date,
        is_primary=(existing == 0), uploaded_by=current_user.id,
    )
    db.add(photo)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        try:
            await run_in_threadpool(_gcs_delete, path)  # best effort: avoid an orphaned object
        except Exception:
            logger.warning("Could not remove orphaned photo object after DB failure")
        raise
    return (await _photo_responses([photo]))[0]


@router.put("/animals/{animal_id}/photos/{photo_id}", response_model=AnimalPhotoResponse)
async def update_animal_photo(
    animal_id: int,
    photo_id: int,
    data: AnimalPhotoUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY)),
):
    photo = await _load_photo(db, animal_id, photo_id)
    if "caption" in data.model_fields_set:
        photo.caption = data.caption
    if "taken_date" in data.model_fields_set:
        photo.taken_date = data.taken_date
    if data.is_primary is not None:
        if data.is_primary:
            await db.execute(
                update(AnimalPhoto)
                .where(and_(AnimalPhoto.animal_id == animal_id, AnimalPhoto.id != photo_id))
                .values(is_primary=False)
            )
        photo.is_primary = data.is_primary
    await db.commit()
    return (await _photo_responses([photo]))[0]


@router.delete("/animals/{animal_id}/photos/{photo_id}")
async def delete_animal_photo(
    animal_id: int,
    photo_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    photo = await _load_photo(db, animal_id, photo_id)
    try:
        await run_in_threadpool(_gcs_delete, photo.gcs_path)  # object first; keep the row if this fails
    except _GCSUnavailable as exc:
        raise HTTPException(status_code=503, detail=f"Photo storage is unavailable: {exc}")
    except Exception as exc:
        logger.warning("Photo delete failed: %s", type(exc).__name__)
        raise HTTPException(status_code=502, detail="Could not delete the photo from storage")
    await db.delete(photo)
    await db.commit()
    return {"message": "Photo deleted"}
