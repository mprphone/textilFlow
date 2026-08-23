from sqlalchemy.orm import Session

from ..models import SequenceCounter


def next_value(db: Session, company_id: int, key: str) -> int:
    """Devolve o proximo numero de uma sequencia (company_id, key), criando-a se necessario."""
    counter = db.query(SequenceCounter).filter_by(company_id=company_id, key=key).with_for_update().first()
    if not counter:
        counter = SequenceCounter(company_id=company_id, key=key, value=0)
        db.add(counter)
        db.flush()
    counter.value += 1
    db.flush()
    return counter.value


def formatted(db: Session, company_id: int, key: str, *, prefix: str = "", width: int = 3, period: str | None = None) -> str:
    """Numero formatado com zeros a esquerda; `period` isola a sequencia (ex.: reinicia por dia)."""
    scoped_key = f"{key}:{period}" if period else key
    value = next_value(db, company_id, scoped_key)
    return f"{prefix}{value:0{width}d}"
