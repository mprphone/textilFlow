from datetime import date, timedelta

from ...auth import hash_password
from ...models import (
    Company, Customer, Department, Employee, Facility, FieldDefinition, FormTemplate,
    Machine, ProductionLine, Supplier, User, UserCompany, WorkflowDefinition,
)
from ..modules import default_enabled_modules


def seed_foundation(db) -> dict:
    company = Company(code="TF", name="TextileFlow Fábrica Demo", tax_id="PT500000001", settings={"enabled_modules": default_enabled_modules()})
    db.add(company)
    db.flush()
    user = User(username="admin", full_name="Administrador", email="admin@textileflow.local", password_hash=hash_password("admin123"), must_change_password=True)
    db.add(user)
    db.flush()
    db.add(UserCompany(user_id=user.id, company_id=company.id, role="admin", permissions=["*"]))

    facility = Facility(company_id=company.id, code="FAB1", name="Fábrica Principal", facility_type="factory")
    db.add(facility)
    db.flush()
    departments = {}
    for code, name, overhead in [
        ("DES", "Desenvolvimento e Amostras", 8.5), ("COR", "Corte", 12.0),
        ("CONF", "Confeção", 9.5), ("ACAB", "Acabamentos", 7.5),
        ("QUAL", "Qualidade", 6.0), ("ARM", "Armazém", 5.0),
    ]:
        department = Department(company_id=company.id, facility_id=facility.id, code=code, name=name, cost_center=code, hourly_overhead=overhead)
        db.add(department)
        db.flush()
        departments[code] = department

    lines = {}
    for code, name, department, mode, minutes, target in [
        ("CORTE", "Sala de Corte", "COR", "batch", 1440, 88),
        ("L1", "Linha 1", "CONF", "line", 3840, 85),
        ("L2", "Linha 2", "CONF", "line", 2880, 82),
        ("AMOST", "Atelier de Amostras", "DES", "piece", 960, 75),
    ]:
        line = ProductionLine(company_id=company.id, department_id=departments[department].id, code=code, name=name, production_mode=mode, capacity_minutes_day=minutes, target_efficiency=target)
        db.add(line)
        db.flush()
        lines[code] = line

    employees = {}
    employee_rows = [
        ("E001", "Ana Martins", "COR", "CORTE", "Cortadora", 9.2, ["estender", "corte manual"]),
        ("E002", "Joana Silva", "COR", "CORTE", "Cortadora", 8.8, ["corte automático", "separação"]),
        ("E003", "Carla Ferreira", "CONF", "L1", "Costureira", 8.4, ["ponto preso", "gola", "mangas"]),
        ("E004", "Marta Costa", "CONF", "L1", "Costureira", 8.2, ["corta-e-cose", "laterais"]),
        ("E005", "Rita Gomes", "CONF", "L2", "Costureira", 8.0, ["recobrimento", "bainha"]),
        ("E006", "Sofia Rocha", "DES", "AMOST", "Modelista/Amostras", 11.5, ["modelagem", "amostras", "fitting"]),
        ("E007", "Paulo Lima", "QUAL", None, "Inspetor Qualidade", 10.0, ["AQL", "auditoria"]),
    ]
    for code, name, department, line, title, hourly, skills in employee_rows:
        employee = Employee(company_id=company.id, department_id=departments[department].id, line_id=lines[line].id if line else None, code=code, name=name, job_title=title, hourly_cost=hourly, skills=skills, badge_code=code)
        db.add(employee)
        db.flush()
        employees[code] = employee

    machines = {}
    machine_rows = [
        ("CUT-AUTO", "Corte Automático", "COR", "CORTE", "cutter", 24.0, 900),
        ("EST-01", "Mesa de Estender 1", "COR", "CORTE", "spreader", 7.5, 500),
        ("PP-01", "Ponto Preso 01", "CONF", "L1", "lockstitch", 3.8, 85),
        ("COS-01", "Corta e Cose 01", "CONF", "L1", "overlock", 4.4, 100),
        ("REC-01", "Recobrimento 01", "CONF", "L2", "coverstitch", 4.9, 75),
    ]
    for code, name, department, line, machine_type, cost, target in machine_rows:
        machine = Machine(company_id=company.id, department_id=departments[department].id, line_id=lines[line].id, code=code, name=name, machine_type=machine_type, hourly_cost=cost, target_units_hour=target, next_maintenance=date.today() + timedelta(days=5))
        db.add(machine)
        db.flush()
        machines[code] = machine

    customers = {}
    for code, name in [("ZARA", "Zara"), ("MANGO", "Mango"), ("MD", "Massimo Dutti")]:
        customer = Customer(company_id=company.id, code=code, name=name, payment_terms="30 dias")
        db.add(customer)
        db.flush()
        customers[code] = customer
    suppliers = {}
    for code, name, supplier_type, score in [
        ("TIN-N", "Tinturaria Norte", "dyeing", 92),
        ("CONF-S", "Confeções Silva", "sewing", 86),
        ("MALHA-P", "Malhas Portugal", "material", 94),
    ]:
        supplier = Supplier(company_id=company.id, code=code, name=name, supplier_type=supplier_type, score=score, lead_time_days=10, weekly_capacity=12000 if supplier_type == "sewing" else 0, piece_cost=1.2 if supplier_type == "sewing" else 0)
        db.add(supplier)
        db.flush()
        suppliers[code] = supplier

    template = FormTemplate(company_id=company.id, entity_type="style", name="Ficha Técnica Base", version=1, schema={"sections": ["Identificação", "Construção", "Medidas", "Qualidade", "Sustentabilidade"]})
    workflow = WorkflowDefinition(company_id=company.id, entity_type="style", name="Desenvolvimento de Artigo", version=1, stages=["conceito", "proto", "fitting", "size_set", "pps", "aprovado", "produção", "arquivado"])
    db.add_all([template, workflow])
    db.flush()
    for order, key, label, data_type, section in [
        (10, "fit", "Fit", "select", "Construção"), (20, "neck_type", "Tipo de gola", "text", "Construção"),
        (30, "wash_care", "Cuidados de lavagem", "textarea", "Qualidade"),
        (40, "certification", "Certificação exigida", "text", "Sustentabilidade"),
        (50, "measurement_table", "Tabela de medidas", "json", "Medidas"),
    ]:
        db.add(FieldDefinition(company_id=company.id, entity_type="style", field_key=key, label=label, data_type=data_type, section=section, display_order=order, options=["Regular", "Slim", "Oversized"] if key == "fit" else []))

    return {"company": company, "user": user, "facility": facility, "departments": departments, "lines": lines, "employees": employees, "machines": machines, "customers": customers, "suppliers": suppliers, "template": template, "workflow": workflow}
