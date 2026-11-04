"""오류 안내는 할 일부터, 기술적인 내용은 짧게 보여 준다."""


def error_message(summary, detail):
    detail = " ".join(str(detail or "").split())
    if not detail:
        return summary
    if len(detail) > 150:
        detail = "…" + detail[-149:]
    return f"{summary}\n\n자세한 내용: {detail}"
