"""Django application definition."""

from django.apps import AppConfig
from django.utils.module_loading import autodiscover_modules
from django.utils.translation import gettext_lazy as _


class VintaDjangoQuestionnairesConfig(AppConfig):
    name = "vinta_django_questionnaires"
    label = "vinta_django_questionnaires"
    verbose_name = _("Questionnaires")
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        # Other apps register their own validators by importing this module,
        # the way they would register admin classes.
        autodiscover_modules("questionnaire_validators")
