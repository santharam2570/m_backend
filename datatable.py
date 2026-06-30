from models import Organization


class LastDataId:
    @staticmethod
    def getOrganizationLastDataId(col):
        try:
            organizations = Organization.objects.order_by(f'-{col}').limit(1)
            if organizations:
                return int(getattr(organizations[0], col))
            return 0
        except Exception:
            return 0
