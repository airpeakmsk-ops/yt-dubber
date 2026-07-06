"""test_parse_ledger — устойчивость парсера леджера к структуре выгрузки 1С.

Регресс-гейт для бага 2026-07-06 (Phase 6 e2e): 1С ВСЕГДА вставляет пустую строку
после строки-артикула. Прежний парсер сбрасывал cur_ean на ЛЮБОЙ не-EAN не-date
строке (включая пустую) → все движения товара становились orphan (0 продаж →
ZeroDivisionError в build_master). Фикс: пустой col0 НЕ сбрасывает cur_ean; только
непустой текст (заголовок нового товара) сбрасывает — чтобы движения безартикульной
группы не утекли в предыдущий EAN.
"""
from __future__ import annotations

import pathlib

import openpyxl
import pytest

from src.parse_ledger import DATA_START, parse_ledger

EAN_A = 4525807270297
EAN_C = 4525807270280


def _make_ledger(tmp_path: pathlib.Path, rows: list[list]) -> pathlib.Path:
    """Собрать xlsx-леджер: DATA_START строк-заголовков + переданные data-строки."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "TDSheet"
    for _ in range(DATA_START):
        ws.append(["Ведомость по партиям", "", "", "", ""])  # шапка (игнорируется)
    for r in rows:
        ws.append(r)
    path = tmp_path / "ledger_synth.xlsx"
    wb.save(path)
    return path


def test_empty_row_after_artikul_keeps_movements(tmp_path):
    """1С вставляет пустую строку после артикула — движения НЕ теряются (не orphan)."""
    # col0=Номенклатура/дата, col1=Документ, col2=Приход, col3=Расход, col4=остаток
    data = [
        ["16CP крючки", "", "", "", 25],       # имя товара
        [EAN_A, "", "", "", 25],               # артикул (EAN)
        ["", "", "", "", 25],                  # ⬅ ПУСТАЯ строка 1С после артикула
        ["10.01.2025 4:00:00", "Поступление товаров", 30, "", 30],   # приход 30
        ["15.01.2025 13:00:00", "Реализация товаров", "", 5, 25],    # продажа 5
    ]
    path = _make_ledger(tmp_path, data)
    prikhod_map, sales, ostatok_map = parse_ledger(path)

    assert prikhod_map.get(EAN_A) == 30, "приход должен учесться, несмотря на пустую строку после артикула"
    q = sales[(sales["ean"] == EAN_A) & (sales["month"] == "Январь 2025 г.")]["qty"]
    assert len(q) == 1 and q.iloc[0] == 5, "продажа (Реализация расход=5) должна привязаться к EAN_A"
    # остаток = Σприход − Σрасход = 30 − 5 = 25
    assert ostatok_map.get(EAN_A) == 25


def test_nameless_group_movements_do_not_leak(tmp_path):
    """Движения безартикульной группы (имя без EAN) НЕ утекают в предыдущий EAN."""
    data = [
        ["Товар A", "", "", "", 25],
        [EAN_A, "", "", "", 25],
        ["", "", "", "", 25],                                   # пустая после артикула
        ["10.01.2025 4:00:00", "Поступление товаров", 30, "", 30],
        ["15.01.2025 13:00:00", "Реализация товаров", "", 5, 25],
        ["", "", "", "", ""],                                   # разделитель
        ["Образцы без штрихкода", "", "", "", 3],               # ⬅ имя БЕЗ артикула
        ["20.01.2025 9:00:00", "Реализация товаров", "", 3, 0], # НЕ должно уйти в EAN_A
        ["", "", "", "", ""],
        ["Товар C", "", "", "", 10],
        [EAN_C, "", "", "", 10],
        ["", "", "", "", 10],                                   # пустая после артикула
        ["05.02.2025 8:00:00", "Поступление товаров", 10, "", 10],
    ]
    path = _make_ledger(tmp_path, data)
    prikhod_map, sales, ostatok_map = parse_ledger(path)

    # EAN_A продажи = ровно 5 (движение безартикульной группы =3 НЕ приплюсовалось)
    qa = sales[sales["ean"] == EAN_A]["qty"].sum()
    assert qa == 5, f"движение безартикульной группы утекло в EAN_A (ожид. 5, факт {qa})"
    # EAN_C распарсился после безартикульной группы
    assert prikhod_map.get(EAN_C) == 10
    # Ни одна продажа не привязана к несуществующему EAN безартикульной группы
    assert set(sales["ean"].unique()) <= {EAN_A, EAN_C}


def test_zero_sales_ledger_has_empty_sales(tmp_path):
    """Леджер без строк-движений с датами → пустые продажи (downstream guard ловит 0)."""
    data = [
        ["Товар A", "", "", "", 25],
        [EAN_A, "", "", "", 25],
        ["", "", "", "", 25],
        # ни одной строки-даты — только имена/артикулы/пустые
        ["Товар C", "", "", "", 10],
        [EAN_C, "", "", "", 10],
        ["", "", "", "", 10],
    ]
    path = _make_ledger(tmp_path, data)
    _prikhod_map, sales, _ostatok_map = parse_ledger(path)
    assert len(sales) == 0, "без строк-движений продаж быть не должно"
