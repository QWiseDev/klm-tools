#!/usr/bin/env python3
"""Download one Douyin share video through the SSR share page."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urljoin, urlparse
from urllib.request import (
    HTTPCookieProcessor,
    HTTPRedirectHandler,
    Request,
    build_opener,
)
from http.cookiejar import CookieJar


RATIOS = ("1080p", "720p", "540p", "360p")
TTWID_URL = "https://ttwid.bytedance.com/ttwid/union/register/"
PLAY_URL = "https://aweme.snssdk.com/aweme/v1/play/"
SHARE_URL_TEMPLATE = "https://www.iesdouyin.com/share/video/{aweme_id}/"
WECHAT_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 "
    "MicroMessenger/8.0.49"
)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        return None


@dataclass(frozen=True)
class Variant:
    ratio: str
    size: int
    url: str
    content_type: str


def request(
    url: str,
    *,
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 20,
    follow_redirects: bool = True,
):
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    if not follow_redirects:
        opener = build_opener(NoRedirect)

    req = Request(url, data=data, headers=headers or {}, method="POST" if data else "GET")
    return opener.open(req, timeout=timeout)


def extract_first_url(text: str) -> str | None:
    match = re.search(r"https?://[^\s，。！？、]+", text)
    if not match:
        return None
    return match.group(0).rstrip(".,;:!?，。；：！？）)]}")


def extract_aweme_id(text: str) -> str:
    url = extract_first_url(text)
    if not url and re.fullmatch(r"\d{10,25}", text.strip()):
        return text.strip()
    if not url:
        raise ValueError("输入里没有可识别的链接或裸 aweme_id")

    parsed = urlparse(url)
    path = parsed.path
    match = re.search(r"/(?:share/)?video/(\d{10,25})", path)
    if match:
        return match.group(1)

    host = parsed.netloc.lower()
    if host.endswith("v.douyin.com"):
        location = resolve_short_link(url)
        match = re.search(r"/(?:share/)?video/(\d{10,25})", urlparse(location).path)
        if match:
            return match.group(1)
        raise ValueError(f"短链跳转地址里没有找到 aweme_id: {location}")

    raise ValueError(f"链接格式不支持或没有找到 aweme_id: {url}")


def resolve_short_link(url: str) -> str:
    try:
        with request(
            url,
            headers={"User-Agent": WECHAT_UA, "Accept": "*/*"},
            timeout=15,
            follow_redirects=False,
        ) as resp:
            return resp.url
    except HTTPError as exc:
        if 300 <= exc.code < 400:
            location = exc.headers.get("Location")
            if location:
                return urljoin(url, location)
        raise


def get_ttwid() -> str:
    payload = {
        "region": "cn",
        "aid": 6383,
        "needFid": False,
        "service": "www.douyin.com",
        "migrate_info": {"ticket": "", "source": "node"},
        "cbUrlProtocol": "https",
        "union": True,
    }
    headers = {
        "User-Agent": WECHAT_UA,
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": "https://www.douyin.com",
        "Referer": "https://www.douyin.com/",
    }
    with request(TTWID_URL, data=json.dumps(payload).encode(), headers=headers, timeout=15) as resp:
        cookie_header = resp.headers.get("Set-Cookie", "")
        body = resp.read()

    cookie = SimpleCookie()
    cookie.load(cookie_header)
    morsel = cookie.get("ttwid")
    if not morsel:
        raise RuntimeError(f"ttwid 注册成功但响应没有 Set-Cookie: {body[:200]!r}")
    return morsel.value


def fetch_share_html(aweme_id: str, ttwid: str) -> tuple[str, str]:
    share_url = SHARE_URL_TEMPLATE.format(aweme_id=aweme_id)
    headers = {
        "User-Agent": WECHAT_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": "https://www.iesdouyin.com/",
        "Cookie": f"ttwid={ttwid}",
    }
    with request(share_url, headers=headers, timeout=25) as resp:
        html = resp.read().decode("utf-8", errors="replace")
    if "window._ROUTER_DATA" not in html:
        raise RuntimeError("share 页没有返回 window._ROUTER_DATA，可能被降级成反爬空壳")
    return share_url, html


def parse_router_data(html: str) -> dict[str, Any]:
    match = re.search(r"<script>\s*window\._ROUTER_DATA\s*=\s*(\{.*?\})\s*</script>", html, re.S)
    if not match:
        raise RuntimeError("没有在 HTML 中找到 window._ROUTER_DATA")
    return json.loads(match.group(1))


def find_video_item(router_data: dict[str, Any], aweme_id: str) -> dict[str, Any]:
    loader_data = router_data.get("loaderData", {})
    for value in loader_data.values():
        if not isinstance(value, dict):
            continue
        video_info = value.get("videoInfoRes")
        if not isinstance(video_info, dict):
            continue
        for item in video_info.get("item_list") or []:
            if isinstance(item, dict) and item.get("aweme_id") == aweme_id:
                return item

    for item in walk_dicts(router_data):
        if item.get("aweme_id") == aweme_id and isinstance(item.get("video"), dict):
            return item

    raise RuntimeError(f"_ROUTER_DATA 中没有找到视频条目: {aweme_id}")


def walk_dicts(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_dicts(child)


def extract_video_token(item: dict[str, Any]) -> str:
    video = item.get("video") or {}
    play_addr = video.get("play_addr") or {}
    token = play_addr.get("uri")
    if isinstance(token, str) and token:
        return token

    for url in play_addr.get("url_list") or []:
        match = re.search(r"[?&]video_id=([^&]+)", url)
        if match:
            return match.group(1)

    raise RuntimeError("视频条目里没有找到 video.play_addr.uri")


def content_range_size(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"/(\d+)\s*$", value)
    return int(match.group(1)) if match else None


def probe_variant(token: str, ratio: str, referer: str) -> Variant | None:
    play_url = f"{PLAY_URL}?video_id={quote(token)}&ratio={quote(ratio)}"
    headers = {
        "User-Agent": WECHAT_UA,
        "Accept": "*/*",
        "Referer": referer,
        "Range": "bytes=0-1",
    }
    for attempt in range(2):
        try:
            with request(play_url, headers=headers, timeout=25) as resp:
                resp.read(2)
                size = content_range_size(resp.headers.get("Content-Range"))
                if size is None:
                    length = resp.headers.get("Content-Length")
                    size = int(length) if length and length.isdigit() else 0
                if size <= 0:
                    return None
                return Variant(
                    ratio=ratio,
                    size=size,
                    url=resp.url,
                    content_type=resp.headers.get("Content-Type", ""),
                )
        except (HTTPError, URLError, TimeoutError):
            if attempt == 1:
                return None
            time.sleep(0.5)
    return None


def probe_variants(token: str, referer: str) -> list[Variant]:
    variants: list[Variant] = []
    seen_sizes: set[int] = set()
    for ratio in RATIOS:
        variant = probe_variant(token, ratio, referer)
        if not variant or variant.size in seen_sizes:
            continue
        seen_sizes.add(variant.size)
        variants.append(variant)
    if not variants:
        raise RuntimeError("没有探测到可下载的 mp4 档位")
    return variants


def probe_all_variants(token: str, referer: str) -> list[Variant]:
    variants = []
    for ratio in RATIOS:
        variant = probe_variant(token, ratio, referer)
        if variant:
            variants.append(variant)
    if not variants:
        raise RuntimeError("没有探测到可下载的 mp4 档位")
    return variants


def variant_to_dict(variant: Variant) -> dict[str, Any]:
    query = parse_qs(urlparse(variant.url).query)
    return {
        "ratio": variant.ratio,
        "size": variant.size,
        "content_type": variant.content_type,
        "br": first_query_value(query, "br"),
        "bt": first_query_value(query, "bt"),
        "url": variant.url,
    }


def first_query_value(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    return values[0] if values else None


def default_output_path(aweme_id: str, ratio: str) -> Path:
    return Path(f"douyin_{aweme_id}_{ratio}.mp4")


def download(variant: Variant, output: Path, referer: str) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    headers = {
        "User-Agent": WECHAT_UA,
        "Accept": "video/mp4,video/*,*/*",
        "Referer": referer,
    }
    tmp_output = output.with_suffix(output.suffix + ".part")
    with request(variant.url, headers=headers, timeout=60) as resp, tmp_output.open("wb") as file:
        total = int(resp.headers.get("Content-Length") or variant.size)
        copied = 0
        while True:
            chunk = resp.read(1024 * 256)
            if not chunk:
                break
            file.write(chunk)
            copied += len(chunk)
            if total:
                print(f"\r下载中: {copied}/{total} bytes", end="", file=sys.stderr)
        print(file=sys.stderr)

    if variant.size and tmp_output.stat().st_size != variant.size:
        print(
            f"警告: 探测大小为 {variant.size} bytes，实际下载 {tmp_output.stat().st_size} bytes",
            file=sys.stderr,
        )
    os.replace(tmp_output, output)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="通过 Douyin SSR share 页下载单个视频，支持短链、长链和裸 aweme_id。"
    )
    parser.add_argument("input", help="分享文本、v.douyin.com 短链、douyin.com/video 长链或裸 aweme_id")
    parser.add_argument("-o", "--output", type=Path, help="输出 mp4 路径")
    parser.add_argument("--list", action="store_true", help="只列出探测到的画质档，不下载")
    parser.add_argument("--urls", action="store_true", help="输出各 ratio 的最终 CDN 地址，不下载")
    parser.add_argument(
        "--ratio",
        choices=RATIOS,
        help="指定下载 ratio；若该 ratio 与更高档重复，仍按指定 ratio 下载",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        aweme_id = extract_aweme_id(args.input)
        print(f"aweme_id: {aweme_id}", file=sys.stderr)

        ttwid = get_ttwid()
        share_url, html = fetch_share_html(aweme_id, ttwid)
        router_data = parse_router_data(html)
        item = find_video_item(router_data, aweme_id)
        token = extract_video_token(item)
        print(f"video_id: {token}", file=sys.stderr)

        if args.ratio:
            variant = probe_variant(token, args.ratio, share_url)
            if not variant:
                raise RuntimeError(f"指定 ratio 不可用: {args.ratio}")
            variants = [variant]
        elif args.urls:
            variants = probe_all_variants(token, share_url)
        else:
            variants = probe_variants(token, share_url)

        for index, variant in enumerate(variants, start=1):
            print(
                f"{index}. ratio={variant.ratio} size={variant.size} "
                f"type={variant.content_type or '-'}",
                file=sys.stderr,
            )

        if args.urls:
            print(json.dumps([variant_to_dict(item) for item in variants], ensure_ascii=False, indent=2))
            return 0

        if args.list:
            return 0

        selected = variants[0]
        output = args.output or default_output_path(aweme_id, selected.ratio)
        download(selected, output, share_url)
        print(str(output.resolve()))
        return 0
    except Exception as exc:
        with contextlib.suppress(Exception):
            tmp_files = list(Path(".").glob("*.mp4.part"))
            for tmp_file in tmp_files:
                tmp_file.unlink()
        print(f"错误: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
