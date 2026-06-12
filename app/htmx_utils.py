from fastapi import Request


def is_fragment_request(request: Request) -> bool:
    """True for htmx fragment swaps, not boosted full-page navigation."""
    return bool(request.headers.get("HX-Request")) and not request.headers.get("HX-Boosted")
