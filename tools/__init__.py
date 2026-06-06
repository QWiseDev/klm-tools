"""Tool registry for the local toolbox."""

from __future__ import annotations

from . import douyin_video


TOOLS = (douyin_video,)


def tool_manifest() -> list[dict]:
    return [tool.META for tool in TOOLS]


def route_get(handler, parsed, *, send_body: bool) -> bool:
    return any(tool.route_get(handler, parsed, send_body=send_body) for tool in TOOLS)


def route_post(handler, parsed) -> bool:
    return any(tool.route_post(handler, parsed) for tool in TOOLS)
