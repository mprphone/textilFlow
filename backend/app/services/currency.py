"""Conversao cambial pragmatica.

Nao e um modulo de tesouraria: uma so taxa manual por moeda/data
(ExchangeRate), sem historico de mercado nem multiplas fontes. O objetivo e
parar de somar/comparar valores em moedas diferentes como se fossem iguais -
uma ficha de custo em USD deixa de contaminar silenciosamente os totais em
EUR de outras fichas.
"""

from __future__ import annotations

from datetime import date

from ..models import Company, ExchangeRate


def base_currency(company: Company | None) -> str:
    return (company.currency if company and company.currency else "EUR").upper()


def latest_rate(db, company_id: int, currency: str, on_date: date | None = None) -> ExchangeRate | None:
    query = db.query(ExchangeRate).filter_by(company_id=company_id, currency=currency.upper())
    if on_date:
        row = query.filter(ExchangeRate.effective_date <= on_date).order_by(ExchangeRate.effective_date.desc()).first()
        if row:
            return row
    return query.order_by(ExchangeRate.effective_date.desc()).first()


def convert_to_base(db, company: Company, amount: float, currency: str | None, on_date: date | None = None) -> dict:
    """amount esta em `currency`; devolve o equivalente em base_currency(company).

    Se `currency` for None ou igual a base, devolve o valor tal e qual
    (rate=1, fx_missing=False). Se for outra moeda sem taxa configurada,
    devolve amount=None e fx_missing=True - o chamador decide como mostrar
    isso, em vez de fingir uma taxa 1:1 que estaria errada.
    """
    base = base_currency(company)
    currency = (currency or base).upper()
    if currency == base:
        return {"amount": round(amount, 4), "rate": 1.0, "currency": base, "fx_missing": False}
    rate_row = latest_rate(db, company.id, currency, on_date)
    if not rate_row:
        return {"amount": None, "rate": None, "currency": base, "fx_missing": True}
    return {"amount": round(amount * rate_row.rate_to_base, 4), "rate": rate_row.rate_to_base, "currency": base, "fx_missing": False}
