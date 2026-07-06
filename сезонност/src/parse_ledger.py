"""parse_ledger — единый источник движений товара из «приходы остатки.xlsx».

1С «Ведомость по партиям товаров»: иерархия
    строка-имя товара  (col0=имя, col2/3 — БИТЫЕ субитоги, не использовать)
    строка-артикул EAN (col0=EAN, субитоги тоже битые)
    строки-детализация (col0=дата, col1=документ, col2=Приход кол-во, col3=Расход кол-во, col4=ост)
    ... затем следующий товар.

Субитоги 1С неверны у 1127/1325 товаров — считаем ТОЛЬКО детализацию.

Правила агрегации (решения пользователя 2026-06-29):
  ПРИХОД (закупки)      = Поступление − Возврат товаров поставщику.
  ПРОДАНО (нетто, помес.) = Σ по {Реализация, Возврат от покупателя, Комплектация,
                            Оприходование} вклада (Расход − Приход) за месяц.
    - Реализация: расход → +продажа.
    - Возврат от покупателя: приход (товар вернулся) → −продажа; его расход → +продажа.
    - Комплектация/Оприходование в Приходе → −продажа месяца (вернули ошибочно списанное).
    - Комплектация в Расходе → +продажа месяца (реально ушло / продано под видом другого).
  ИГНОР для продаж и прихода: Перемещение (внутренний перенос, нетто 0),
    «Объект не найден» (неизвестный документ), Корректировки (микрообъём — учитываем в
    своих категориях ниже).

Колонки в Sheets-отчёте используют qty; revenue/profit/margin в леджере НЕТ — при
регенерации prodazhi.parquet эти столбцы заполняются 0.0 (в отчёте не отображаются).

Месяц-метка в формате prodazhi.parquet: «<Русский месяц> <год> г.» (как parse_prodazhi).
"""
from __future__ import annotations

import pathlib
import re
import sys

import pandas as pd
import python_calamine

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.normalize import normalize_ean  # noqa: E402

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
LEDGER_PATH = PROJECT_ROOT / "приходы остатки.xlsx"

# col0=Номенклатура/дата, col1=Документ, col2=Приход, col3=Расход, col4=ост.
COL_NOM = 0
COL_DOC = 1
COL_PRI = 2
COL_RAS = 3
DATA_START = 11  # первые строки — заголовки/метаданные

_DATE_RE = re.compile(r"^(\d{2})\.(\d{2})\.(\d{4})")

# month num -> Русское название (как в parse_prodazhi / report_metrics.RU_MONTHS).
_NUM_TO_RU = {
    1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель", 5: "Май", 6: "Июнь",
    7: "Июль", 8: "Август", 9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь",
}


def _num(x) -> float:
    s = str(x).strip().replace(",", ".")
    try:
        return float(s)
    except (TypeError, ValueError):
        return 0.0


def month_label(year: int, month: int) -> str:
    """(2023, 10) -> «Октябрь 2023 г.» (формат prodazhi.parquet)."""
    return f"{_NUM_TO_RU[month]} {year} г."


def _doc_kind(doc: str) -> str:
    """Классификация документа движения по префиксу."""
    d = doc.strip()
    if d.startswith("Поступление"):
        return "postuplenie"
    if d.startswith("Возврат товаров поставщику"):
        return "vozvrat_postavshchiku"
    if d.startswith("Возврат товаров от покупателя"):
        return "vozvrat_pokupatel"
    if d.startswith("Реализация"):
        return "realizaciya"
    if d.startswith("Комплектация"):
        return "komplektaciya"
    if d.startswith("Оприходование"):
        return "oprihodovanie"
    if d.startswith("Корректировка реализации"):
        return "realizaciya"        # корректировка продажи -> в продажи
    if d.startswith("Корректировка поступления"):
        return "postuplenie"        # корректировка прихода -> в приход
    if d.startswith("Перемещение"):
        return "peremeshchenie"     # внутренний перенос -> игнор (в продажи не идёт)
    return "other"                  # «Объект не найден» и пр. -> считаем как продажу (user 2026-06-29)


# Типы документов, влияющие на ПРОДАЖИ (вклад = расход − приход за месяц).
# «other» = «Объект не найден» и прочие нераспознанные: расход = продажа, приход = −продажа
# (решение пользователя 2026-06-29). Перемещение в продажи НЕ входит.
_SALE_KINDS = {"realizaciya", "vozvrat_pokupatel", "komplektaciya", "oprihodovanie", "other"}


def parse_ledger(path: pathlib.Path | None = None):
    """Распарсить леджер. Возвращает (prikhod_map, sales_long_df).

    prikhod_map:   dict[ean(int) -> приход_нетто (Поступление − Возврат поставщику)].
    sales_long_df: DataFrame[ean(int), month(str), qty(float)] — НЕТТО-продажи по месяцам
                   (только месяцы с ненулевым нетто; формат месяца как в prodazhi.parquet).
    """
    path = pathlib.Path(path) if path is not None else LEDGER_PATH
    wb = python_calamine.CalamineWorkbook.from_path(str(path))
    rows = wb.get_sheet_by_name(wb.sheet_names[0]).to_python()

    prikhod_map: dict[int, float] = {}
    ostatok_map: dict[int, float] = {}        # Σприход − Σрасход по всем движениям = конечный остаток
    sales: dict[tuple[int, str], float] = {}  # (ean, month_label) -> qty net
    cur_ean: int | None = None
    orphan_rows = 0                            # строки-движения без активного EAN (безартикульные группы)

    for r in rows[DATA_START:]:
        c0 = str(r[COL_NOM]).strip() if len(r) > COL_NOM else ""
        ean = normalize_ean(r[COL_NOM]) if len(r) > COL_NOM else None
        if ean is not None:
            cur_ean = int(ean)
            prikhod_map.setdefault(cur_ean, 0.0)
            ostatok_map.setdefault(cur_ean, 0.0)
            continue
        # Классификация НЕ-EAN строки по col0:
        #   • Пустой col0 → 1С вставляет пустую строку ПОСЛЕ артикула и как
        #     разделитель между товарами; она НЕ завершает блок EAN — движения
        #     товара идут после неё. Сброс здесь терял ВСЕ движения (orphan).
        #     Пропускаем без сброса cur_ean.
        #   • Непустой текст (не дата) → заголовок нового товара, в т.ч.
        #     безартикульного; сбрасываем cur_ean, чтобы движения безартикульной
        #     группы (образцы) не утекли в предыдущий EAN.
        if not _DATE_RE.match(c0):
            if c0 != "":
                cur_ean = None
            continue
        if cur_ean is None:
            orphan_rows += 1
            continue
        year, month = int(_DATE_RE.match(c0).group(3)), int(_DATE_RE.match(c0).group(2))
        pri, ras = _num(r[COL_PRI]), _num(r[COL_RAS])
        kind = _doc_kind(str(r[COL_DOC]))

        # Остаток = сумма всех физических движений (любой тип): приход − расход.
        ostatok_map[cur_ean] += pri - ras

        if kind == "postuplenie":
            prikhod_map[cur_ean] += pri
        elif kind == "vozvrat_postavshchiku":
            prikhod_map[cur_ean] -= ras
        elif kind in _SALE_KINDS:
            # вклад в продажи месяца = расход − приход
            sales[(cur_ean, month_label(year, month))] = (
                sales.get((cur_ean, month_label(year, month)), 0.0) + (ras - pri)
            )
        # peremeshchenie / other -> в остаток уже учтены, в приход/продажи не идут

    if orphan_rows:
        print(f"[parse_ledger] orphan-строк без EAN пропущено: {orphan_rows} (безартикульные группы)")

    sales_rows = [
        {"ean": e, "month": mlabel, "qty": q}
        for (e, mlabel), q in sales.items()
        if abs(q) > 1e-9
    ]
    sales_long = pd.DataFrame(sales_rows, columns=["ean", "month", "qty"])
    return prikhod_map, sales_long, ostatok_map


INTERIM = PROJECT_ROOT / "data" / "interim"
PRODAZHI_OUT = INTERIM / "prodazhi.parquet"
PRIKHOD_LEDGER_OUT = INTERIM / "prikhod_ledger.parquet"


def write_artifacts(path: pathlib.Path | None = None) -> tuple[int, int]:
    """Записать prodazhi.parquet (продажи из леджера) + prikhod_ledger.parquet (приход).

    prodazhi.parquet схема = как у parse_prodazhi (ean, month, qty, revenue_rub,
    profit_rub, margin_pct), но revenue/profit/margin = 0.0 (в леджере денег нет;
    в Sheets-отчёте эти колонки не используются). Возвращает (n_sales_rows, n_eans).
    """
    prikhod_map, sales_long, ostatok_map = parse_ledger(path)
    INTERIM.mkdir(parents=True, exist_ok=True)

    sales = sales_long.copy()
    sales["revenue_rub"] = 0.0
    sales["profit_rub"] = 0.0
    sales["margin_pct"] = 0.0
    sales = sales[["ean", "month", "qty", "revenue_rub", "profit_rub", "margin_pct"]]
    sales.to_parquet(PRODAZHI_OUT, engine="pyarrow", index=False)

    # приход + остаток (Σприход−Σрасход = конечный остаток) из леджера в один артефакт.
    pri = pd.DataFrame(
        [{"ean": e, "qty_prikhod": q, "qty_stock": ostatok_map.get(e, 0.0)}
         for e, q in prikhod_map.items()],
        columns=["ean", "qty_prikhod", "qty_stock"],
    )
    pri.to_parquet(PRIKHOD_LEDGER_OUT, engine="pyarrow", index=False)
    return len(sales), len(prikhod_map)


def main() -> None:
    n_sales, n_eans = write_artifacts()
    prikhod_map, sales_long, _ = parse_ledger()
    total_sold = sales_long.groupby("ean")["qty"].sum()
    print(
        f"ledger: {n_eans} EAN | приход сумм={sum(prikhod_map.values()):.0f} | "
        f"продажи строк={n_sales} | месяцев={sales_long['month'].nunique()} | "
        f"продано всего сумм={total_sold.sum():.0f}"
    )
    print(f"-> {PRODAZHI_OUT}\n-> {PRIKHOD_LEDGER_OUT}")


if __name__ == "__main__":
    main()
