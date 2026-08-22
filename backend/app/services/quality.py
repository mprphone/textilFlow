"""Ajuda de amostragem AQL para inspecoes de qualidade.

IMPORTANTE: nao e a tabela ANSI/ASQ Z1.4 (ISO 2859-1) completa - reproduz os
tamanhos de amostra reais da Tabela I / II-A (nivel geral II), que sao um
dado publico estavel, mas o numero de aceitacao/rejeicao usa uma
aproximacao (Ac = floor(n x AQL / 100), Re = Ac + 1) em vez dos valores
exatos da tabela, que dependem de "setas" e nao seguem uma formula fechada.
Serve para uma sugestao rapida no posto de inspecao; para compromissos
contratuais de AQL com o cliente, usar a tabela oficial.
"""

from __future__ import annotations

LOT_SIZE_BREAKPOINTS = [
    (8, "A", 2), (15, "B", 3), (25, "C", 5), (50, "D", 8), (90, "E", 13),
    (150, "F", 20), (280, "G", 32), (500, "H", 50), (1200, "J", 80),
    (3200, "K", 125), (10000, "L", 200), (35000, "M", 315),
    (150000, "N", 500), (500000, "P", 800),
]


def aql_sample_plan(lot_size: float, aql_pct: float = 2.5, inspection_level: str = "II") -> dict:
    lot_size = max(1, int(lot_size or 0))
    aql_pct = float(aql_pct or 2.5)
    code_letter, sample_size = "Q", 1250
    for max_lot, letter, n in LOT_SIZE_BREAKPOINTS:
        if lot_size <= max_lot:
            code_letter, sample_size = letter, n
            break
    sample_size = min(sample_size, lot_size)
    level_factor = {"I": 0.4, "II": 1.0, "III": 1.6}.get(inspection_level, 1.0)
    sample_size = max(2, round(sample_size * level_factor)) if inspection_level != "II" else sample_size
    accept = max(0, int((sample_size * aql_pct / 100) // 1))
    reject = accept + 1
    return {
        "lot_size": lot_size,
        "aql_pct": aql_pct,
        "inspection_level": inspection_level,
        "code_letter": code_letter,
        "sample_size": sample_size,
        "accept_max_defects": accept,
        "reject_min_defects": reject,
        "note": "Aproximação prática (Ac = amostra × AQL/100). Para compromissos contratuais de AQL, use a tabela ANSI/ASQ Z1.4 oficial.",
    }
