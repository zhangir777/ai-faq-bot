"""Save leads to an Excel file (one row per lead)."""

import re
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font

HEADERS = ["Date", "Name", "Phone", "Question", "Telegram", "User id"]
WIDTHS = [18, 20, 16, 60, 18, 14]


def normalize_phone(raw: str) -> str | None:
    """+7XXXXXXXXXX for KZ/RU numbers written as 8..., +7..., 7..., with spaces/brackets."""
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 11 and digits[0] in "78":
        return "+7" + digits[1:]
    if len(digits) == 10:
        return "+7" + digits
    return None


def save_lead(path: Path, name: str, phone: str, question: str, username: str, user_id: int):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        wb = load_workbook(path)
        ws = wb.active
    else:
        wb = Workbook()
        ws = wb.active
        ws.title = "Leads"
        ws.append(HEADERS)
        for cell in ws[1]:
            cell.font = Font(bold=True)
        for col, width in zip("ABCDEF", WIDTHS, strict=True):
            ws.column_dimensions[col].width = width
        ws.freeze_panes = "A2"
    date = datetime.now().strftime("%Y-%m-%d %H:%M")
    ws.append([date, name, phone, question, f"@{username}" if username else "-", user_id])
    wb.save(path)
