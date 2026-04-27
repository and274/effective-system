from datetime import datetime


def now_iso() -> str:
    return datetime.now().isoformat()
