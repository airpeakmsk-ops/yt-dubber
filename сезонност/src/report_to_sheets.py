"""report_to_sheets — orchestrator: собрать отчёт (Plan 01) → записать в лист «Отчёт».

Связывает офлайн-сборку (build_report.build_report_df + df_to_rows, доказана в Plan 01)
с тонким сетевым слоем (sheets_client.get_client + write_report, Plan 02).

build_rows() — чистая, без сети, тестируема офлайн (переиспользует Plan 01).
main() — касается сети; выполняется только при живом прогоне после human-action gate
(Editor-доступ сервис-аккаунту), НЕ в pytest. На импорте модуля main() НЕ вызывается.
"""
from __future__ import annotations

import pathlib
import sys

# Allow `python src/report_to_sheets.py` to run standalone (project root on path).
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.build_report import build_report_df, df_to_rows  # noqa: E402
from src.sheets_client import get_client, write_report  # noqa: E402

# LOCKED targets (зафиксировано пользователем / research'ем).
SHEET_ID = "1ncF3ElaK8OWRfnajrdkiK9WcNQQ9r0UTKhx_xSaBtSE"
WORKSHEET_TITLE = "Отчёт"


def build_rows() -> list[list]:
    """Собрать отчётный DataFrame (Plan 01) и сериализовать в Sheets-safe list[list].

    Чистая офлайн-функция: НЕ касается сети, переиспользует проверенный пайплайн Plan 01.
    rows[0] — заголовки, далее 1300 строк данных; всё сериализуемо (str/число/"").
    """
    df = build_report_df()
    return df_to_rows(df)


def main() -> None:
    """Живой прогон: собрать строки и идемпотентно записать в лист «Отчёт».

    Касается сети — запускать только вручную после предоставления Editor-доступа
    сервис-аккаунту (human-action gate). НЕ часть автоматической pytest-сьюты.
    """
    rows = build_rows()
    client = get_client()
    ss = client.open_by_key(SHEET_ID)
    n = write_report(ss, WORKSHEET_TITLE, rows)
    print(f"Записано строк: {n} в лист «{WORKSHEET_TITLE}»")


if __name__ == "__main__":
    main()
