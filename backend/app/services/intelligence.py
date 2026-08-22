from ..models import ProductionOrder
from .cost_control import order_control
from .fabric_flow import fabric_delay_risk


def operational_briefing(db, company_id: int, dashboard: dict) -> dict:
    priorities = []
    controls = []
    orders = db.query(ProductionOrder).filter_by(company_id=company_id).all()
    for order in orders:
        data = order.custom_data or {}
        for alert in data.get("fabric_alerts") or []:
            if alert.get("seen"):
                continue
            priorities.append({
                "severity": "warning",
                "area": "Malha",
                "title": alert.get("title") or f"Malha · {order.order_no}",
                "explanation": alert.get("detail") or "Deu entrada de malha para esta OF.",
                "action": "Abrir corte",
                "route": "corte",
                "score": 90,
            })
        if data.get("fabric_ready") is False and order.status not in {"completed", "cancelled"}:
            risk = fabric_delay_risk(db, order)
            if risk["at_risk"]:
                priorities.append({
                    "severity": "danger", "area": "Prazo", "title": f"{order.order_no} · malha atrasada",
                    "explanation": risk["reason"] or "A malha prevista chega depois do corte necessário.",
                    "action": "Ver compras", "route": "inventory", "score": 92,
                })
            else:
                priorities.append({
                    "severity": "warning", "area": "Malha", "title": f"{order.order_no} no plano sem malha",
                    "explanation": "A OF já pode estar planeada. Quando a malha der entrada, aparece o alerta para a saída ao corte.",
                    "action": "Ver compras", "route": "inventory", "score": 80,
                })
        control = order_control(db, order)
        controls.append(control)
        if not control["baseline"] and order.status not in {"completed", "cancelled"}:
            priorities.append({
                "severity": "danger", "area": "Custos", "title": f"{order.order_no} sem orçamento aprovado",
                "explanation": "A produção está sem uma referência de custo; não é possível medir a margem real.",
                "action": "Criar ou aprovar proposta", "route": "costing", "score": 100,
            })
        elif control["baseline"] and control["metrics"].get("deviation_pct", 0) > 5:
            priorities.append({
                "severity": "danger", "area": "Custos", "title": f"{order.order_no} acima do orçamento",
                "explanation": f"O custo real ultrapassa o permitido em {control['metrics']['deviation_pct']:.1f}% ({control['metrics']['deviation']:.2f} €).",
                "action": "Analisar o desvio", "route": "costing", "score": 95,
            })

    for order in dashboard["orders"]:
        if order["planned_end"] and order["progress"] < 100:
            priorities.append({
                "severity": "warning", "area": "Prazo", "title": f"Confirmar capacidade de {order['order_no']}",
                "explanation": f"Está a {order['progress']:.1f}% e tem conclusão prevista para {order['planned_end']}.",
                "action": "Ver rasto da OF", "route": "tracking", "score": 75,
            })

    for alert in dashboard["alerts"]:
        route = "inventory" if "Lote" in alert["title"] else "machines" if "Manutenção" in alert["title"] else "partners"
        priorities.append({
            "severity": alert["type"], "area": "Exceção", "title": alert["title"],
            "explanation": alert["detail"], "action": "Resolver agora", "route": route,
            "score": 85 if alert["type"] == "danger" else 60,
        })

    for line in dashboard["lines"]:
        if line["hours"] and line["efficiency"] < line["target"]:
            priorities.append({
                "severity": "warning", "area": "Produção", "title": f"{line['name']} abaixo do objetivo",
                "explanation": f"Eficiência real de {line['efficiency']:.1f}% para um objetivo de {line['target']:.1f}%.",
                "action": "Ver produção em direto", "route": "live", "score": 70,
            })

    priorities = sorted(priorities, key=lambda item: item["score"], reverse=True)
    danger = sum(item["severity"] == "danger" for item in priorities)
    warnings = sum(item["severity"] == "warning" for item in priorities)
    health_score = max(0, min(100, 100 - danger * 16 - warnings * 6))
    cost_risks = sum(bool(item["baseline"]) and item["metrics"].get("deviation_pct", 0) > 5 for item in controls)
    without_baseline = sum(not item["baseline"] for item in controls)
    if danger:
        narrative = f"Existem {danger} situações críticas. Comece pela primeira prioridade para proteger prazo e margem."
    elif warnings:
        narrative = f"A operação está controlada, com {warnings} pontos que merecem atenção hoje."
    else:
        narrative = "A operação está estável. Não existem desvios críticos neste momento."
    return {
        "health_score": health_score,
        "narrative": narrative,
        "critical_count": danger,
        "warning_count": warnings,
        "cost_risks": cost_risks,
        "without_cost_baseline": without_baseline,
        "priorities": priorities[:8],
        "questions": [
            "O que devo resolver primeiro?", "Onde estamos a perder dinheiro?",
            "Que ordens podem atrasar?", "Como está a eficiência das linhas?",
        ],
    }
