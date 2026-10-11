from django.apps import AppConfig


class FspMockConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "fsp_mock"
    verbose_name = "FSP Mock IdP and Registry"
