from pydantic import BaseModel


class UploadResumeResponse(BaseModel):
    doc_id: str
    filename: str
    text_preview: str
    text_chars: int


class PresignedUrlResponse(BaseModel):
    doc_id: str
    upload_key: str
    download_url: str