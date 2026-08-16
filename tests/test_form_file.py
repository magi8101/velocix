"""Tests for Form/File parameter injection and multipart request.form().

Covers: urlencoded + multipart request.form(), Form/File markers (Annotated
and classic styles), UploadFile contents, required/default/alias semantics,
422s, and mixed field+file bodies.
"""

import asyncio
from typing import Annotated

from velocix import File, Form, Query, TestClient, UploadFile, Velocix


def _run(coro):
    return asyncio.run(coro)


def _multipart_body(boundary: str, fields: dict[str, str], files: dict[str, tuple[str, bytes]]) -> bytes:
    """Build a multipart/form-data body with both fields and file parts."""
    parts = []
    for name, value in fields.items():
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        parts.append(value.encode() + b"\r\n")
    for name, (filename, content) in files.items():
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode()
        )
        parts.append(b"Content-Type: application/octet-stream\r\n\r\n")
        parts.append(content)
        parts.append(b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts)


def _post_form(client, fields=None, files=None, headers=None, path="/"):
    boundary = "BoundaryXYZ123"
    body = _multipart_body(boundary, fields or {}, files or {})
    return client.post(
        path,
        body=body,
        headers={
            "content-type": f"multipart/form-data; boundary={boundary}",
            **(headers or {}),
        },
    )


def test_request_form_urlencoded():
    app = Velocix()

    @app.post("/")
    async def echo(request):
        form = await request.form()
        return {"a": form.get("a"), "b": form.get("b")}

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.post(
                "/",
                body=b"a=1&b=hello",
                headers={"content-type": "application/x-www-form-urlencoded"},
            )
            assert resp.json() == {"a": "1", "b": "hello"}

    _run(scenario())


def test_request_form_multipart_mixed():
    app = Velocix()

    @app.post("/")
    async def echo(request):
        form = await request.form()
        upload = form["doc"]
        data = await upload.read()
        return {
            "name": form["name"],
            "filename": upload.filename,
            "content_type": upload.content_type,
            "size": len(data),
            "data": data.decode(),
        }

    async def scenario():
        async with TestClient(app) as client:
            resp = await _post_form(
                client,
                fields={"name": "alice"},
                files={"doc": ("note.txt", b"hello world")},
            )
            assert resp.json() == {
                "name": "alice",
                "filename": "note.txt",
                "content_type": "application/octet-stream",
                "size": 11,
                "data": "hello world",
            }

    _run(scenario())


def test_form_marker_annotated():
    app = Velocix()

    @app.post("/")
    async def submit(name: Annotated[str, Form()], age: Annotated[int, Form()] = 0):
        return {"name": name, "age": age}

    async def scenario():
        async with TestClient(app) as client:
            resp = await _post_form(client, fields={"name": "alice", "age": "30"})
            assert resp.json() == {"name": "alice", "age": 30}
            # missing optional field -> default
            resp = await _post_form(client, fields={"name": "bob"})
            assert resp.json() == {"name": "bob", "age": 0}

    _run(scenario())


def test_form_marker_classic_style():
    app = Velocix()

    @app.post("/")
    async def submit(name: str = Form(...)):  # type: ignore[assignment]
        return {"name": name}

    async def scenario():
        async with TestClient(app) as client:
            assert (await _post_form(client, fields={"name": "x"})).json() == {"name": "x"}

    _run(scenario())


def test_form_required_missing_is_422():
    app = Velocix()

    @app.post("/")
    async def submit(name: Annotated[str, Form()]):
        return {"name": name}

    async def scenario():
        async with TestClient(app) as client:
            assert (await _post_form(client, fields={})).status_code == 422

    _run(scenario())


def test_form_alias():
    app = Velocix()

    @app.post("/")
    async def submit(full_name: Annotated[str, Form(alias="name")]):
        return {"full_name": full_name}

    async def scenario():
        async with TestClient(app) as client:
            assert (await _post_form(client, fields={"name": "alice"})).json() == {
                "full_name": "alice"
            }

    _run(scenario())


def test_file_marker_returns_upload_file():
    app = Velocix()

    @app.post("/upload")
    async def upload(doc: Annotated[UploadFile, File()]):
        data = await doc.read()
        return {
            "filename": doc.filename,
            "content_type": doc.content_type,
            "size": len(data),
        }

    async def scenario():
        async with TestClient(app) as client:
            resp = await _post_form(client, files={"doc": ("a.bin", b"\x00\x01\x02")}, path="/upload")
            assert resp.json() == {
                "filename": "a.bin",
                "content_type": "application/octet-stream",
                "size": 3,
            }

    _run(scenario())


def test_file_optional_missing_uses_default():
    app = Velocix()

    @app.post("/upload")
    async def upload(doc: Annotated[UploadFile | None, File()] = None):
        return {"has_doc": doc is not None}

    async def scenario():
        async with TestClient(app) as client:
            assert (await _post_form(client, files={}, path="/upload")).json() == {
                "has_doc": False
            }
            assert (
                await _post_form(client, files={"doc": ("a.bin", b"x")}, path="/upload")
            ).json() == {"has_doc": True}

    _run(scenario())


def test_file_required_missing_is_422():
    app = Velocix()

    @app.post("/upload")
    async def upload(doc: Annotated[UploadFile, File()]):
        return {"filename": doc.filename}

    async def scenario():
        async with TestClient(app) as client:
            assert (await _post_form(client, files={}, path="/upload")).status_code == 422
            # a plain field with the file's name is not a file -> 422
            assert (
                await _post_form(client, fields={"doc": "not a file"}, path="/upload")
            ).status_code == 422

    _run(scenario())


def test_form_and_file_together():
    app = Velocix()

    @app.post("/")
    async def submit(title: Annotated[str, Form()], doc: Annotated[UploadFile, File()]):
        data = await doc.read()
        return {"title": title, "size": len(data)}

    async def scenario():
        async with TestClient(app) as client:
            resp = await _post_form(
                client,
                fields={"title": "report"},
                files={"doc": ("r.pdf", b"pdf-data")},
            )
            assert resp.json() == {"title": "report", "size": 8}

    _run(scenario())


def test_form_with_query_and_body_coexistence():
    app = Velocix()

    @app.post("/")
    async def submit(name: Annotated[str, Form()], tag: Annotated[str, Query()] = "none"):
        return {"name": name, "tag": tag}

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.post(
                "/?tag=fast",
                body=_multipart_body("B", {"name": "x"}, {}),
                headers={"content-type": "multipart/form-data; boundary=B"},
            )
            assert resp.json() == {"name": "x", "tag": "fast"}

    _run(scenario())


def test_request_form_empty_body():
    app = Velocix()

    @app.post("/")
    async def echo(request):
        return dict(await request.form())

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.post("/", body=b"", headers={"content-type": "application/x-www-form-urlencoded"})
            assert resp.json() == {}

    _run(scenario())


def test_request_form_malformed_multipart_is_400():
    app = Velocix()

    @app.post("/")
    async def echo(request):
        return dict(await request.form())

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.post(
                "/",
                body=b"--noboundary--\r\n",
                headers={"content-type": "multipart/form-data; boundary=missing"},
            )
            assert resp.status_code == 400

    _run(scenario())
