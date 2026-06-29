"""Phase 4 (расширение) — формирование заказа из листов-входов (order_finalize).

Чистые офлайн-тесты: парсеры листов + формулы (исключить / уже заказано / хотелки /
лимит завода). Правила — решения пользователя 2026-06-29.
"""
from __future__ import annotations

import pandas as pd
import pytest

try:
    from src.order_finalize import (
        adjusted_report_order,
        apply_report_order_adjustment,
        build_coverage_block,
        build_order_rows,
        dealer_coverage,
        final_order_qty,
        parse_already_ordered,
        parse_dealer_wants,
        parse_exclude,
        parse_factory_avail,
    )
    _OK = True
except ImportError:
    _OK = False

_skip = pytest.mark.skipif(not _OK, reason="src.order_finalize not implemented")


@_skip
def test_parse_exclude():
    vals = [["4525807317558"], ["4525807317480"], [""], ["мусор"]]
    assert parse_exclude(vals) == {4525807317558, 4525807317480}


@_skip
def test_parse_already_and_wants():
    already = [["EAN", "Наим", "Кол-во заказано", "Себест", ""],
               ["4525807299304", "X", "1", "95,46", "95,46"],
               ["4525807299328", "Y", "16", "95,46", "1527,36"]]
    assert parse_already_ordered(already) == {4525807299304: 1.0, 4525807299328: 16.0}
    wants = [["", "ДОЛГОВ", "ХОТЕЛКИ", "ИТОГО", ""],
             ["4525807328448", "Z", "12", "7,60", "91,20"]]
    assert parse_dealer_wants(wants) == {4525807328448: 12.0}


@_skip
def test_parse_factory_avail():
    vals = [["", "", "", "", ""],
            ["4525807328448", "THIN", "FUJIKAWA", "$7,60", "8"],
            ["4525807171167", "TRIC", "SILVER", "$6,35", "62"]]
    assert parse_factory_avail(vals) == {4525807328448: 8.0, 4525807171167: 62.0}


@_skip
def test_adjusted_report_order():
    assert adjusted_report_order(10.0, 3.0, False) == 7.0
    assert adjusted_report_order(5.0, 10.0, False) == 0.0      # минус ушёл в 0 (прогноз был числом)
    assert adjusted_report_order(20.0, 0.0, True) == 0          # исключён -> 0
    assert adjusted_report_order("", 0.0, False) == ""          # нет прогноза -> ""


@_skip
def test_final_order_qty():
    # прогноз 20, хотелки 14 -> 20 (берём большее)
    assert final_order_qty(20.0, 14.0, 0.0, False) == 20.0
    # прогноз 10, хотелки 24 -> 24
    assert final_order_qty(10.0, 24.0, 0.0, False) == 24.0
    # уже заказано вычитается: max(20,14)=20 - 5 = 15
    assert final_order_qty(20.0, 14.0, 5.0, False) == 15.0
    # исключён -> 0
    assert final_order_qty(20.0, 14.0, 0.0, True) == 0.0
    # прогноз "" (неэлигибл), хотелки 8 -> 8
    assert final_order_qty("", 8.0, 0.0, False) == 8.0


@_skip
def test_dealer_coverage():
    assert dealer_coverage(12.0, 8.0) == (8.0, 4.0)     # 8 покроется, 4 нет
    assert dealer_coverage(5.0, 20.0) == (5.0, 0.0)     # завод покрывает всё
    assert dealer_coverage(5.0, None) == (5.0, 0.0)     # нет в листе лимита -> без огр.


@_skip
def test_build_order_rows_and_total():
    df = pd.DataFrame({
        "EAN": [111, 222, 333],
        "Наименование": ["A", "B", "C"],
        "Себестоимость USD": [10.0, 5.0, 2.0],
        "К заказу на 2 мес": [20.0, "", 0.0],
    })
    excluded = {333}
    already = {111: 5.0}
    wants = {222: 8.0}
    rows = build_order_rows(df, excluded, already, wants)
    assert rows[0] == ["EAN", "Наименование", "Себестоимость USD", "Кол-во к заказу", "Сумма USD"]
    body = {r[0]: r for r in rows[1:-1]}
    # 111: max(20,0)-5=15 *10 =150 ; 222: max(0,8)=8 *5=40 ; 333 исключён -> нет
    assert body[111][3] == 15.0 and body[111][4] == 150.0
    assert body[222][3] == 8.0 and body[222][4] == 40.0
    assert 333 not in body
    assert rows[-1][0] == "ИТОГО" and rows[-1][4] == 190.0


@_skip
def test_apply_report_order_adjustment():
    df = pd.DataFrame({
        "EAN": [111, 222],
        "К заказу на 2 мес": [10.0, 20.0],
    })
    out = apply_report_order_adjustment(df, excluded={222}, already_ordered={111: 4.0})
    vals = dict(zip(out["EAN"], out["К заказу на 2 мес"]))
    assert vals[111] == 6.0   # 10 - 4
    assert vals[222] == 0     # исключён


@_skip
def test_build_coverage_block_aligned():
    dealer_vals = [["", "", "", "", ""],
                   ["", "ДОЛГОВ", "ХОТЕЛКИ", "ИТОГО", ""],
                   ["4525807328448", "Z", "12", "7,60", "91,20"]]
    factory = {4525807328448: 8.0}
    block = build_coverage_block(dealer_vals, factory)
    assert len(block) == 3                       # выровнено по строкам
    assert block[1] == ["Доступно завод", "Покроется", "Не закроется"]
    assert block[2] == [8.0, 8.0, 4.0]           # доступно 8, покроется 8, не закроется 4
