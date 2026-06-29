"""order_finalize — формирование «ближайшего заказа» из листов-входов Google Sheet.

Чистый вычислительный модуль (без сети): парсеры берут уже прочитанные значения листов
(list[list[str]]) и возвращают словари; формулы детерминированы и юнит-тестируемы.

Листы-входы (ведёт пользователь вручную, мы их только читаем):
  «исключить»                  — col0 = EAN; товары, которые больше не заказываем -> заказ 0.
  «уже заказано»               — EAN, наим., Кол-во заказано(col2), себест(col3); вычитаем из заказа.
  «надо дилерам, еще не заказано» — EAN, наим., Хотелки(col2), себест(col3); реальный спрос дилеров.
  «доступный остаток завода»   — EAN, модель, цвет, $себест(col3), Доступно(col4); лимит завода по EAN.

Правила (решения пользователя 2026-06-29):
  Отчёт «К заказу» = max(0, прогноз_2мес − уже_заказано); исключённый EAN -> 0.
  Ближайший заказ кол-во = max(0, max(прогноз_2мес, хотелки) − уже_заказано); исключённый -> 0.
    (прогноз и хотелки НЕ складываются — берём большее; «уже заказано» вычитаем.)
  Лимит завода ограничивает ТОЛЬКО хотелки (для аналитики «не закроется»), не режет заказ:
    покроется = min(хотелки, доступно); не_закроется = max(0, хотелки − доступно).
    EAN нет в листе лимита -> без ограничения (покроется = хотелки, не_закроется = 0).
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.normalize import normalize_ean  # noqa: E402


def _num(x) -> float:
    """'95,46' / '$7,60' / '16' -> float; пусто/мусор -> 0.0."""
    s = str(x).strip().replace("$", "").replace("\xa0", "").replace(" ", "").replace(",", ".")
    try:
        return float(s)
    except (TypeError, ValueError):
        return 0.0


# --- парсеры листов (values = ws.get_all_values()) ---------------------------

def parse_exclude(values: list[list[str]]) -> set[int]:
    """col0 = EAN (без заголовка). Возвращает множество int EAN."""
    out: set[int] = set()
    for row in values:
        if not row:
            continue
        e = normalize_ean(row[0])
        if e is not None:
            out.add(int(e))
    return out


def _parse_ean_qty(values: list[list[str]], qty_col: int) -> dict[int, float]:
    """Общий парсер: EAN в col0, количество в qty_col. Строки без валидного EAN пропускаются."""
    out: dict[int, float] = {}
    for row in values:
        if not row:
            continue
        e = normalize_ean(row[0])
        if e is None:
            continue
        q = _num(row[qty_col]) if len(row) > qty_col else 0.0
        out[int(e)] = out.get(int(e), 0.0) + q
    return out


def parse_already_ordered(values: list[list[str]]) -> dict[int, float]:
    """«уже заказано»: Кол-во заказано в col2."""
    return _parse_ean_qty(values, qty_col=2)


def parse_dealer_wants(values: list[list[str]]) -> dict[int, float]:
    """«надо дилерам»: хотелки в col2."""
    return _parse_ean_qty(values, qty_col=2)


def parse_factory_avail(values: list[list[str]]) -> dict[int, float]:
    """«доступный остаток завода»: доступно в col4 (последняя колонка)."""
    return _parse_ean_qty(values, qty_col=4)


# --- формулы -----------------------------------------------------------------

def _as_float(prognoz) -> float:
    """Прогноз «К заказу» из отчёта может быть "" (неэлигибл) -> 0.0."""
    if prognoz == "" or prognoz is None:
        return 0.0
    try:
        v = float(prognoz)
        return 0.0 if v < 0 else v
    except (TypeError, ValueError):
        return 0.0


def adjusted_report_order(prognoz, already_ordered: float, excluded: bool) -> float | str:
    """Отчёт «К заказу» с учётом исключения и уже заказанного.

    excluded -> 0. Иначе max(0, прогноз − уже_заказано). "" прогноз трактуем как 0,
    но если результат 0 и прогноз был "" — возвращаем "" (нет дозаказа), иначе число.
    """
    if excluded:
        return 0
    p = _as_float(prognoz)
    val = max(0.0, p - max(0.0, already_ordered))
    if val == 0.0 and (prognoz == "" or prognoz is None):
        return ""
    return round(val, 1)


def final_order_qty(prognoz, hotelki: float, already_ordered: float, excluded: bool) -> float:
    """Кол-во в «ближайший заказ» = max(0, max(прогноз, хотелки) − уже_заказано); исключ. -> 0."""
    if excluded:
        return 0.0
    base = max(_as_float(prognoz), max(0.0, hotelki))
    return max(0.0, round(base - max(0.0, already_ordered), 1))


def dealer_coverage(hotelki: float, avail) -> tuple[float, float]:
    """(покроется, не_закроется) хотелок при лимите завода.

    avail = доступно на заводе (float) или None (нет в листе лимита -> без ограничения).
    """
    h = max(0.0, hotelki)
    if avail is None:
        return h, 0.0
    a = max(0.0, float(avail))
    return min(h, a), max(0.0, h - a)


# --- билдеры строк для записи в Sheets ---------------------------------------

_EAN_COL = "EAN"
_NAME_COL = "Наименование"
_COST_COL = "Себестоимость USD"
_PROG_COL = "К заказу на 2 мес"


def apply_report_order_adjustment(df, excluded: set[int], already_ordered: dict[int, float]):
    """Вернуть копию df с пересчитанной колонкой «К заказу на 2 мес» (Отчёт).

    Исключённые EAN -> 0; иначе max(0, прогноз − уже_заказано). Прогноз "" -> "".
    """
    df = df.copy()
    new = []
    for ean, prog in zip(df[_EAN_COL], df[_PROG_COL]):
        e = int(ean)
        new.append(adjusted_report_order(prog, already_ordered.get(e, 0.0), e in excluded))
    df[_PROG_COL] = new
    return df


def build_order_rows(df, excluded: set[int], already_ordered: dict[int, float],
                     dealer_wants: dict[int, float]) -> list[list]:
    """Строки листа «ближайший заказ»: EAN, наим., себест, кол-во, сумма + ИТОГО.

    Кол-во = max(0, max(прогноз, хотелки) − уже_заказано); исключённые -> 0.
    Себестоимость — из df (cost_usd_wavg). Сортировка по сумме строки убыв.
    Прогноз берётся ИЗ ИСХОДНОГО df (до adjust), чтобы не вычесть «уже заказано» дважды.
    """
    header = ["EAN", "Наименование", "Себестоимость USD", "Кол-во к заказу", "Сумма USD"]
    body: list[list] = []
    total_qty = 0.0
    total_sum = 0.0
    for row in df.itertuples(index=False):
        d = dict(zip(df.columns, row))
        e = int(d[_EAN_COL])
        qty = final_order_qty(
            d.get(_PROG_COL, ""), dealer_wants.get(e, 0.0),
            already_ordered.get(e, 0.0), e in excluded,
        )
        if qty <= 0:
            continue
        cost = d.get(_COST_COL, 0.0)
        cost = float(cost) if cost not in ("", None) else 0.0
        line = round(qty * cost, 2)
        total_qty += qty
        total_sum += line
        body.append([e, d.get(_NAME_COL, ""), round(cost, 2), qty, line])
    body.sort(key=lambda r: r[4], reverse=True)
    return [header] + body + [["ИТОГО", "", "", round(total_qty, 1), round(total_sum, 2)]]


def build_coverage_block(dealer_values: list[list[str]], factory_avail: dict[int, float],
                         header_marker: str = "ХОТЕЛКИ") -> list[list]:
    """Блок из 3 колонок, выровненный по строкам листа «надо дилерам».

    Для строки с валидным EAN: [доступно_завод | "", покроется, не_закроется].
    Для строки-заголовка (содержит header_marker) — подписи колонок.
    Прочие строки — пустые. dealer_wants берём из col2 той же строки.
    """
    block: list[list] = []
    for row in dealer_values:
        e = normalize_ean(row[0]) if row else None
        if e is not None:
            hot = _num(row[2]) if len(row) > 2 else 0.0
            avail = factory_avail.get(int(e))
            covered, unmet = dealer_coverage(hot, avail)
            avail_cell = "" if avail is None else round(float(avail), 1)
            block.append([avail_cell, round(covered, 1), round(unmet, 1)])
        elif row and any(header_marker in str(c) for c in row):
            block.append(["Доступно завод", "Покроется", "Не закроется"])
        else:
            block.append(["", "", ""])
    return block
