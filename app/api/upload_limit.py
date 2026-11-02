"""Rejects oversized upload requests before FastAPI parses the multipart body.

The exact per-file limit is enforced again while the file is copied into storage; this middleware
stops a huge request from being spooled to disk first.
"""

from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import error_response
from app.schemas.common import ErrorCode

# Room for multipart boundaries and part headers on top of the file itself.
MULTIPART_OVERHEAD_BYTES = 64 * 1024


class UploadSizeLimitMiddleware:
    def __init__(self, app: ASGIApp, path: str, max_file_bytes: int) -> None:
        self.app = app
        self.path = path
        self.max_file_bytes = max_file_bytes
        self.max_body_bytes = max_file_bytes + MULTIPART_OVERHEAD_BYTES

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] != "POST" or scope["path"] != self.path:
            await self.app(scope, receive, send)
            return

        headers = dict(scope["headers"])
        content_length = headers.get(b"content-length", b"")
        if content_length.isdigit() and int(content_length) > self.max_body_bytes:
            response = error_response(
                413,
                ErrorCode.FILE_TOO_LARGE,
                f"File exceeds the maximum upload size of {self.max_file_bytes // (1024 * 1024)} MB.",
                {"max_bytes": self.max_file_bytes},
            )
            await response(scope, receive, send)
            return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body_bytes:
                    raise HTTPException(status_code=413)
            return message

        await self.app(scope, limited_receive, send)
