"""Django application definition."""

from django.apps import AppConfig
from django.utils.module_loading import autodiscover_modules
from django.utils.translation import gettext_lazy as _

from vinta_django_questionnaires import conf

# Before any model in this package is imported -- see the docstring for why
# that matters, and why this is not in ``ready()``.
conf.install_swappable_defaults()


class VintaDjangoQuestionnairesConfig(AppConfig):
    name = "vinta_django_questionnaires"
    label = "vinta_django_questionnaires"
    verbose_name = _("Questionnaires")
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        # Other apps register their own validators by importing this module,
        # the way they would register admin classes.
        autodiscover_modules("questionnaire_validators")
