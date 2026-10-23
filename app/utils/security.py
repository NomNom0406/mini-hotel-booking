import bleach

ALLOWED_TAGS: list[str] = [] #Không cho phép HTML trong input người dùng
ALLOWED_ATTRIBUTES: dict ={}

def sanitize(text: str) -> str:
    """Strip toàn bộ HTML ra khỏi input người dùng."""
    return bleach.clean(text, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES, strip=True)