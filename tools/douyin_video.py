"""Douyin share video tool."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from http import HTTPStatus
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, unquote, urlparse
from urllib.request import Request, urlopen

from douyin_download import (
    WECHAT_UA,
    extract_aweme_id,
    extract_first_url,
    extract_video_token,
    fetch_share_html,
    find_video_item,
    get_ttwid,
    parse_router_data,
    probe_variants,
    variant_to_dict,
)


META = {
    "id": "douyin-video",
    "name": "分享视频",
    "category": "抖音",
    "description": "粘贴分享地址，获取可用分辨率、预览和下载视频。",
    "status": "ready",
}

CACHE_TTL_SECONDS = 20 * 60
CHUNK_SIZE = 256 * 1024


@dataclass
class MediaEntry:
    aweme_id: str
    ratio: str
    size: int
    content_type: str
    url: str
    referer: str
    filename: str
    created_at: float


MEDIA_CACHE: dict[str, MediaEntry] = {}


def route_get(handler, parsed, *, send_body: bool) -> bool:
    if parsed.path.startswith("/api/douyin/media/"):
        handle_media(handler, parsed.path, parsed.query, send_body=send_body)
        return True
    return False


def route_post(handler, parsed) -> bool:
    if parsed.path == "/api/douyin/resolve":
        handle_resolve(handler)
        return True
    return False


def handle_resolve(handler) -> None:
    try:
        data = handler.read_json_body()
        input_text = str(data.get("input") or "").strip()
        if not input_text:
            raise ValueError("请输入包含 https://v.douyin.com 短链的抖音分享内容")
        short_url = normalize_douyin_short_url(input_text)
        result = resolve_video(short_url)
    except Exception as exc:
        handler.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
        return

    handler.send_json(result)


def normalize_douyin_short_url(input_text: str) -> str:
    url = extract_first_url(input_text) or input_text.strip()
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc.lower() != "v.douyin.com":
        raise ValueError("仅支持 https://v.douyin.com 开头的抖音短链")
    return url


def resolve_video(input_text: str) -> dict[str, Any]:
    short_url = normalize_douyin_short_url(input_text)
    aweme_id = extract_aweme_id(short_url)
    ttwid = get_ttwid()
    share_url, html = fetch_share_html(aweme_id, ttwid)
    router_data = parse_router_data(html)
    item = find_video_item(router_data, aweme_id)
    token = extract_video_token(item)
    variants = probe_variants(token, share_url)

    return {
        "tool": META["id"],
        "aweme_id": aweme_id,
        "title": item.get("desc") or f"抖音视频 {aweme_id}",
        "author": ((item.get("author") or {}).get("nickname")) or "",
        "cover": first_url(((item.get("video") or {}).get("cover") or {}).get("url_list")),
        "share_url": share_url,
        "input_url": short_url,
        "video_id": token,
        "variants": [store_variant(aweme_id, variant, share_url) for variant in variants],
    }


def first_url(urls: Any) -> str:
    if isinstance(urls, list) and urls:
        first = urls[0]
        return first if isinstance(first, str) else ""
    return ""


def store_variant(aweme_id: str, variant, referer: str) -> dict[str, Any]:
    prune_media_cache()
    media_id = hashlib.sha256(
        f"{aweme_id}|{variant.ratio}|{variant.size}|{variant.url}|{time.time_ns()}".encode()
    ).hexdigest()[:20]
    filename = f"douyin_{aweme_id}_{variant.ratio}.mp4"
    MEDIA_CACHE[media_id] = MediaEntry(
        aweme_id=aweme_id,
        ratio=variant.ratio,
        size=variant.size,
        content_type=variant.content_type or "video/mp4",
        url=variant.url,
        referer=referer,
        filename=filename,
        created_at=time.time(),
    )
    payload = variant_to_dict(variant)
    payload.update(
        {
            "id": media_id,
            "filename": filename,
            "media_url": f"/api/douyin/media/{media_id}",
            "download_url": f"/api/douyin/media/{media_id}?download=1",
        }
    )
    return payload


def prune_media_cache() -> None:
    now = time.time()
    expired = [
        media_id
        for media_id, entry in MEDIA_CACHE.items()
        if now - entry.created_at > CACHE_TTL_SECONDS
    ]
    for media_id in expired:
        del MEDIA_CACHE[media_id]


def handle_media(handler, path: str, query: str, *, send_body: bool) -> None:
    prune_media_cache()
    media_id = unquote(path.rsplit("/", 1)[-1])
    entry = MEDIA_CACHE.get(media_id)
    if not entry:
        handler.send_error_json(HTTPStatus.NOT_FOUND, "媒体地址已过期，请重新解析")
        return

    params = parse_qs(query)
    attachment = params.get("download") == ["1"]
    if not send_body:
        send_media_headers(handler, HTTPStatus.OK, entry, attachment=attachment)
        return

    headers = {
        "User-Agent": WECHAT_UA,
        "Accept": "video/mp4,video/*,*/*",
        "Referer": entry.referer,
    }
    range_header = handler.headers.get("Range")
    if range_header:
        headers["Range"] = range_header

    try:
        req = Request(entry.url, headers=headers)
        with urlopen(req, timeout=60) as resp:
            handler.send_response(HTTPStatus(resp.status))
            copy_media_headers(handler, resp.headers, entry, attachment=attachment)
            handler.end_headers()
            while True:
                chunk = resp.read(CHUNK_SIZE)
                if not chunk:
                    break
                handler.wfile.write(chunk)
    except HTTPError as exc:
        handler.send_error_json(HTTPStatus.BAD_GATEWAY, f"CDN 请求失败: HTTP {exc.code}")
    except (URLError, TimeoutError) as exc:
        handler.send_error_json(HTTPStatus.BAD_GATEWAY, f"CDN 请求失败: {exc}")
    except BrokenPipeError:
        return


def send_media_headers(handler, status: HTTPStatus, entry: MediaEntry, *, attachment: bool) -> None:
    handler.send_response(status)
    handler.send_header("Content-Type", entry.content_type or "video/mp4")
    handler.send_header("Content-Length", str(entry.size))
    handler.send_header("Accept-Ranges", "bytes")
    handler.send_header("Cache-Control", "no-store")
    if attachment:
        handler.send_header("Content-Disposition", f'attachment; filename="{entry.filename}"')
    handler.end_headers()


def copy_media_headers(handler, headers, entry: MediaEntry, *, attachment: bool) -> None:
    for key in ("Content-Type", "Content-Length", "Content-Range", "Accept-Ranges"):
        value = headers.get(key)
        if value:
            handler.send_header(key, value)
    if not headers.get("Content-Type"):
        handler.send_header("Content-Type", entry.content_type or "video/mp4")
    handler.send_header("Cache-Control", "no-store")
    if attachment:
        handler.send_header("Content-Disposition", f'attachment; filename="{entry.filename}"')
