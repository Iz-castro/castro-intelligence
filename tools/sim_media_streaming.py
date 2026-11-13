# -*- coding: utf-8 -*-
"""Contratos HTTP reais de midia, GCS fake e concorrencia, sem acesso externo.

Rodar com o Python do venv principal: tools/sim_media_streaming.py.
Nao inicia lifespan nem usa credenciais ou dados de clientes.
"""

import asyncio
from contextlib import ExitStack
import gzip
import logging
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx
from google.api_core.exceptions import NotFound

import main
import media

logging.getLogger("httpx").setLevel(logging.WARNING)


class FakeBlob:
    def __init__(self, content):
        self.content = content
        self.size = len(content)
        self.content_type = "video/mp4"
        self.generation = 123
        self.downloads = []
        self.on_reload = lambda: None
        self.on_download = lambda: None

    def reload(self):
        self.on_reload()

    def download_as_bytes(self, **kwargs):
        self.on_download()
        self.downloads.append(kwargs)
        assert kwargs["raw_download"] is True
        assert kwargs["if_generation_match"] == self.generation
        return self.content[kwargs["start"]:kwargs["end"] + 1]


class MediaStreamingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.folder = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.stack.enter_context(patch.object(media, "MEDIA_DIR", str(self.folder)))
        self.stack.enter_context(patch.object(media, "MEDIA_STORAGE_BACKEND", "local"))
        self.stack.enter_context(patch("socket.socket.connect", side_effect=AssertionError("Rede externa proibida")))
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test")
        self.addAsyncCleanup(self.client.aclose)
        self.content = b"0123456789abcdefghijklmnopqrstuvwxyz"
        self.url = self.local_asset("video", "sample.mp4", self.content)

    def local_asset(self, subdir, filename, content):
        folder = self.folder / subdir
        folder.mkdir(exist_ok=True)
        (folder / filename).write_bytes(content)
        return f"/media/{subdir}/{filename}"

    def gcs(self, content):
        blob = FakeBlob(content)
        bucket = Mock()
        bucket.blob.return_value = blob
        self.stack.enter_context(patch.object(media, "MEDIA_STORAGE_BACKEND", "gcs"))
        self.stack.enter_context(patch.object(media, "GCS_MEDIA_BUCKET", "fake-bucket"))
        self.stack.enter_context(patch.object(media, "_get_bucket", return_value=bucket))
        return blob

    async def test_local_full_and_other_media(self):
        for subdir, filename, mime in (("video", "sample.mp4", "video/mp4"),
                                       ("images", "sample.png", "image/png"),
                                       ("audio", "sample.mp3", "audio/mpeg"),
                                       ("documents", "sample.pdf", "application/pdf")):
            with self.subTest(filename=filename):
                url = self.local_asset(subdir, filename, self.content)
                response = await self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.content, self.content)
                self.assertEqual(response.headers["content-type"], mime)
                self.assertEqual(response.headers["content-length"], str(len(self.content)))
                self.assertEqual(response.headers["accept-ranges"], "bytes")
                self.assertEqual(response.headers["cache-control"], "private, no-store")

    async def test_ranges_and_seek(self):
        for value, start, end in (("bytes=0-1", 0, 1), ("bytes=12-18", 12, 18),
                                  ("bytes=5-", 5, 35), ("bytes=-4", 32, 35),
                                  ("bytes=-999", 0, 35), ("bytes=9-999", 9, 35),
                                  ("bytes=0-0", 0, 0)):
            with self.subTest(range=value):
                response = await self.client.get(self.url, headers={"Range": value})
                self.assertEqual(response.status_code, 206)
                self.assertEqual(response.content, self.content[start:end + 1])
                self.assertEqual(response.headers["content-range"], f"bytes {start}-{end}/36")
                self.assertEqual(response.headers["content-length"], str(end - start + 1))

    async def test_invalid_and_unsupported_ranges(self):
        for value in ("bytes=36-", "bytes=9-4", "bytes=-0", "bytes=-", "bytes=bad", "bytes=1-x"):
            with self.subTest(range=value):
                response = await self.client.get(self.url, headers={"Range": value})
                self.assertEqual(response.status_code, 416)
                self.assertEqual(response.headers["content-range"], "bytes */36")
                self.assertEqual(response.content, b"")
        for value in ("items=0-1", "bytes=0-1,4-5"):
            response = await self.client.get(self.url, headers={"Range": value})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content, self.content)
        response = await self.client.get(self.url, headers={"Range": "bytes=0-1", "If-Range": '"old"'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, self.content)

    async def test_head_empty_and_missing(self):
        response = await self.client.head(self.url, headers={"Range": "bytes=0-1"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-length"], "36")
        self.assertEqual(response.content, b"")
        empty_url = self.local_asset("video", "empty.mp4", b"")
        response = await self.client.get(empty_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"")
        self.assertEqual(response.headers["content-length"], "0")
        response = await self.client.get(empty_url, headers={"Range": "bytes=0-0"})
        self.assertEqual(response.status_code, 416)
        self.assertEqual(response.headers["content-range"], "bytes */0")
        self.assertEqual((await self.client.get("/media/video/missing.mp4")).status_code, 404)

    async def test_gcs_lazy_bounded_and_generation_pinned(self):
        content = b"x" * (media.MEDIA_STREAM_CHUNK_SIZE * 3 + 17)
        blob = self.gcs(content)
        source = media.get_media_stream(self.url)
        self.assertEqual(source["size"], len(content))
        self.assertEqual(blob.downloads, [])
        for method, headers, status in (("HEAD", {}, 200), ("GET", {"Range": "bytes=99999999-"}, 416)):
            response = await self.client.request(method, self.url, headers=headers)
            self.assertEqual(response.status_code, status)
            self.assertEqual(blob.downloads, [])
        response = await self.client.get(self.url, headers={"Range": "bytes=10-20"})
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.content, content[10:21])
        self.assertEqual([(d["start"], d["end"]) for d in blob.downloads], [(10, 20)])
        blob.downloads.clear()
        response = await self.client.get(self.url)
        self.assertEqual(response.content, content)
        self.assertEqual(len(blob.downloads), 4)
        self.assertTrue(all(d["end"] - d["start"] + 1 <= media.MEDIA_STREAM_CHUNK_SIZE for d in blob.downloads))
        self.assertEqual(blob.downloads[0]["start"], 0)
        self.assertEqual(blob.downloads[-1]["end"], len(content) - 1)

    async def test_gcs_missing_preserves_local_fallback(self):
        blob = self.gcs(self.content)
        blob.on_reload = Mock(side_effect=NotFound("Objeto inexistente"))
        response = await self.client.get(self.url, headers={"Range": "bytes=0-1"})
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.content, self.content[:2])
        self.assertEqual(blob.downloads, [])
        response = await self.client.get("/media/video/missing.mp4")
        self.assertEqual(response.status_code, 404)

    async def test_legacy_firestore_compression_and_range(self):
        packed = gzip.compress(self.content)
        asset_ref = Mock()
        asset_ref.get.return_value.exists = True
        asset_ref.get.return_value.to_dict.return_value = {"mime_type": "video/mp4", "content_encoding": "gzip"}
        asset_ref.get.return_value.reference = asset_ref
        chunks = [Mock(), Mock()]
        chunks[0].to_dict.return_value = {"seq": 1, "data": packed[10:]}
        chunks[1].to_dict.return_value = {"seq": 0, "data": packed[:10]}
        asset_ref.collection.return_value.stream.return_value = chunks
        with patch.object(media, "MEDIA_STORAGE_BACKEND", "firestore"), patch.object(media, "_firestore_asset_ref", return_value=asset_ref):
            response = await self.client.get(self.url, headers={"Range": "bytes=2-8"})
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.content, self.content[2:9])
        self.assertEqual(response.headers["content-range"], "bytes 2-8/36")

    async def test_slow_storage_does_not_block_other_requests(self):
        blob = self.gcs(self.content)
        loop = asyncio.get_running_loop()
        loop_thread = threading.get_ident()
        for hook in ("on_reload", "on_download"):
            with self.subTest(operation=hook):
                entered = asyncio.Event()
                release = threading.Event()

                def slow_storage():
                    self.assertNotEqual(threading.get_ident(), loop_thread)
                    loop.call_soon_threadsafe(entered.set)
                    if not release.wait(5):
                        raise AssertionError("Teste nao liberou a leitura")

                setattr(blob, hook, slow_storage)
                pending = asyncio.create_task(self.client.get(self.url))
                try:
                    await asyncio.wait_for(entered.wait(), timeout=3)
                    response = await asyncio.wait_for(self.client.get("/api/client-config"), timeout=2)
                    self.assertEqual(response.status_code, 200)
                finally:
                    release.set()
                    response = await asyncio.wait_for(pending, timeout=3)
                    setattr(blob, hook, lambda: None)
                self.assertEqual(response.content, self.content)


if __name__ == "__main__":
    unittest.main(verbosity=2)
