import pytest
from openpyxl import load_workbook

from bot.leads import HEADERS, normalize_phone, save_lead


@pytest.mark.parametrize(
    ("raw", "phone"),
    [
        ("8 777 123 45 67", "+77771234567"),
        ("+7 (777) 123-45-67", "+77771234567"),
        ("7771234567", "+77771234567"),
        ("+1 (415) 555-0100", "+14155550100"),
        ("+44 20 7946 0958", "+442079460958"),
        ("+123", None),
        ("12345", None),
        ("", None),
    ],
)
def test_normalize_phone(raw, phone):
    assert normalize_phone(raw) == phone


def test_save_lead_appends_rows(tmp_path):
    path = tmp_path / "data" / "leads.xlsx"
    save_lead(path, "Айгуль", "+77771234567", "Сколько стоит маникюр?", "aigul", 1)
    save_lead(path, "Bob", "+77001112233", "-", "", 2)
    rows = list(load_workbook(path).active.values)
    assert list(rows[0]) == HEADERS
    assert rows[1][1:] == ("Айгуль", "+77771234567", "Сколько стоит маникюр?", "@aigul", 1)
    assert rows[2][4] == "-"
