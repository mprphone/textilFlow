from .analytics import dashboard_metrics, employee_performance, machine_performance
from .intelligence import operational_briefing


def answer_factory_question(db, company_id: int, question: str) -> dict:
    normalized = question.lower()
    dashboard = dashboard_metrics(db, company_id)
    briefing = operational_briefing(db, company_id, dashboard)
    actions = []

    if any(word in normalized for word in ("primeiro", "prioridade", "resolver", "hoje")):
        top = briefing["priorities"][:3]
        if top:
            answer = "Comece por: " + " ".join(f"{index + 1}) {row['title']}." for index, row in enumerate(top))
            actions = [{"label": row["action"], "route": row["route"]} for row in top]
        else:
            answer = "A operação está estável. Não existem ações urgentes neste momento."
    elif any(word in normalized for word in ("risco", "atras", "prazo")):
        if dashboard["orders_at_risk"]:
            orders = [row["order_no"] for row in dashboard["orders"] if row["planned_end"]][:3]
            answer = f"Existem {dashboard['orders_at_risk']} ordens em risco. Analise primeiro: {', '.join(orders)}."
        else:
            answer = "Não existem ordens sinalizadas em risco neste momento."
        actions = [{"label": "Ver rasto das OF", "route": "tracking"}]
    elif any(word in normalized for word in ("funcion", "operador", "eficiência")):
        rows = employee_performance(db, company_id)
        best = rows[0] if rows else None
        answer = f"A melhor eficiência registada é de {best['name']}: {best['efficiency']}%, com {best['good']} peças boas." if best else "Ainda não existem registos por funcionário."
        actions = [{"label": "Ver análise por funcionário", "route": "reports"}]
    elif any(word in normalized for word in ("máquina", "maquina", "equipamento")):
        rows = machine_performance(db, company_id)
        active = [row for row in rows if row["hours"] > 0]
        answer = f"Há {len(active)} máquinas com produção registada. Custo acumulado: {sum(row['cost'] for row in active):.2f} €."
        actions = [{"label": "Ver máquinas", "route": "machines"}]
    elif any(word in normalized for word in ("custo", "margem", "dinheiro")):
        answer = f"O custo direto registado é {dashboard['direct_cost']:.2f} €, para {dashboard['output_good']:.0f} unidades boas. Existem {briefing['cost_risks']} ordens acima do orçamento e {briefing['without_cost_baseline']} sem proposta aprovada."
        actions = [{"label": "Analisar custo real", "route": "costing"}]
    elif any(word in normalized for word in ("qualidade", "defeito", "rejeitad")):
        answer = f"A taxa de qualidade atual é {dashboard['quality_rate']:.1f}%. Foram registadas {dashboard['output_rejected']:.0f} peças rejeitadas na produção."
        actions = [{"label": "Abrir qualidade", "route": "quality"}]
    elif any(word in normalized for word in ("stock", "material", "compr")):
        stock_alerts = [row for row in dashboard["alerts"] if "Lote" in row["title"]]
        answer = f"Existem {len(stock_alerts)} alertas de stock que exigem atenção." if stock_alerts else "Não existem ruturas de stock sinalizadas."
        actions = [{"label": "Ver stocks e compras", "route": "inventory"}]
    else:
        answer = f"Estão ativas {dashboard['orders_active']} ordens, com {dashboard['completion_pct']}% concluído e qualidade de {dashboard['quality_rate']}%. {briefing['narrative']}"

    return {
        "answer": answer,
        "source": "live_database",
        "question": question,
        "actions": actions,
        "facts": [
            {"label": "Saúde operacional", "value": f"{briefing['health_score']}%"},
            {"label": "Prioridades", "value": str(len(briefing["priorities"]))},
        ],
    }
