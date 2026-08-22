from .services.primavera import public_status


class PrimaveraConnector:
    """Contrato isolado para a Web API Primavera v10."""

    def __init__(self, company):
        self.company = company

    def status(self):
        return public_status(self.company)
