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
        is_lure,
        move_excluded_to_bottom,
        parse_already_ordered,
        parse_dealer_wants,
        parse_exclude,
        parse_factory_avail,
        round_order_qty,
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
def test_is_lure_and_round():
    assert is_lure("Воблер TIMON TRICOROLL") is True
    assert is_lure("APEED! 2.3g Блесна Timon") is True
    assert is_lure("Спиннинг TIMON T-CONNECTION") is False
    assert is_lure("16CP №8 крючки TIMON") is False
    # приманка -> вверх до кратного 4; аксессуар -> вверх до целого
    assert round_order_qty(15.0, "Воблер X") == 16
    assert round_order_qty(16.0, "Блесна X") == 16
    assert round_order_qty(8.0, "Спиннинг X") == 8
    assert round_order_qty(8.1, "крючки X") == 9
    assert round_order_qty(0.0, "Воблер X") == 0


@_skip
def test_build_order_rows_and_total():
    df = pd.DataFrame({
        "EAN": [111, 222, 333],
        "Наименование": ["Воблер A", "Спиннинг B", "Блесна C"],
        "Себестоимость USD": [10.0, 5.0, 2.0],
        "Остаток": [2.0, 0.0, 1.0],
        "Скорость, шт/мес": [5.0, 1.0, 0.0],
        "К заказу на 2 мес": [20.0, "", 0.0],
    })
    excluded = {333}
    already = {111: 5.0}
    wants = {222: 8.0}
    rows = build_order_rows(df, excluded, already, wants)
    assert rows[0] == ["EAN", "Наименование", "Себестоимость USD", "Текущее наличие",
                       "Скорость шт/мес", "Кол-во к заказу", "Для дилеров", "Сумма USD"]
    body = {r[0]: r for r in rows[1:-1]}
    # 111 приманка: max(20,0)-5=15 -> кратно 4 = 16; сумма 16*10=160; для дилеров 0
    assert body[111][3] == 2.0 and body[111][4] == 5.0
    assert body[111][5] == 16 and body[111][6] == 0 and body[111][7] == 160.0
    # 222 аксессуар: max(0,8)=8 -> 8; сумма 40; для дилеров min(8,8)=8
    assert body[222][5] == 8 and body[222][6] == 8 and body[222][7] == 40.0
    assert 333 not in body                              # исключён
    assert rows[-1][0] == "ИТОГО" and rows[-1][5] == 24 and rows[-1][6] == 8 and rows[-1][7] == 200.0


@_skip
def test_move_excluded_to_bottom():
    df = pd.DataFrame({"EAN": [1, 2, 3, 4], "x": ["a", "b", "c", "d"]})
    out = move_excluded_to_bottom(df, excluded={2})
    assert list(out["EAN"]) == [1, 3, 4, 2]            # 2 вниз, порядок прочих сохранён


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
def test_build_coverage_block_distributes_pool():
    # один EAN в ДВУХ строках дилеров; на заводе всего 22 -> распределить, не дублировать
    dealer_vals = [["", "ДОЛГОВ", "ХОТЕЛКИ", "ИТОГО", ""],
                   ["4525807190137", "A", "12", "6,21", ""],
                   ["4525807190137", "B", "16", "6,21", ""],
                   ["4525807328448", "Z", "5", "7,60", ""]]
    factory = {4525807190137: 22.0, 4525807328448: 8.0}
    block = build_coverage_block(dealer_vals, factory)
    assert block[0] == ["Доступно завод (всего)", "Покроется", "Не закроется"]
    # строка1: покроется 12, остаток пула 10, всего 22 (первое упоминание)
    assert block[1] == [22.0, 12.0, 0.0]
    # строка2: покроется min(16,10)=10, не закроется 6, «всего» пусто (не первое)
    assert block[2] == ["", 10.0, 6.0]
    # Σ покроется по 190137 = 22 == лимит (инвариант пула)
    assert block[1][1] + block[2][1] == 22.0
    # другой EAN: 5 из 8 -> покроется 5
    assert block[3] == [8.0, 5.0, 0.0]
