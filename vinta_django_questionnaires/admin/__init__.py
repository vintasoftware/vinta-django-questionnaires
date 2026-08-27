"""The admin for Vinta Django Questionnaires.

Importing this module registers everything, the way a Django app's `admin`
module is expected to.  What it registers is arranged around what someone
actually does rather than around the model graph:

- **A questionnaire** is a list of versions with a way into each one.
- **A version** has its own settings on the ordinary change form, and
  everything *in* it -- pages, sections, questions, choices, validators -- on
  one structure editor, so a change that touches six of them is one save.
- **Responses** have a table view with a column per question and a CSV export
  of exactly the columns on screen, and each response shows what it wrote and
  what it set off.

Registering is a choice, though, because a project may already have an admin
for these models or may want a different base class under them.  Turn it off
and do it yourself::

    QUESTIONNAIRES_REGISTER_ADMIN = False

and then, in your own ``admin.py``::

    from vinta_django_questionnaires.admin import register

    register()

``register()`` takes the bases to put underneath, which is the whole of what a
themed admin needs.  For `django-unfold <https://unfoldadmin.com>`_::

    from unfold.admin import ModelAdmin, StackedInline, TabularInline

    register(model_admin_base=ModelAdmin, inline_base=TabularInline)

Its own pages -- the structure editor, the response table -- are styled from
`static/vinta_django_questionnaires/admin.css`, which reads the Django admin's
colour tokens and falls back to theme-neutral greys where a project has
replaced them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.contrib import admin

from vinta_django_questionnaires.admin.definition import (
    PageAdmin,
    QuestionAdmin,
    QuestionnaireAdmin,
    QuestionnaireAssets,
    QuestionnaireVersionAdmin,
    QuestionnaireWidgetAdmin,
    SectionAdmin,
    ValueSetAdmin,
)
from vinta_django_questionnaires.admin.editing import (
    AcknowledgedEditAdminMixin,
    AcknowledgedEditInlineMixin,
    signed_form,
)
from vinta_django_questionnaires.admin.integrations import (
    MappingRunAdmin,
    ResponseMappingAdmin,
    ResponseWebhookAdmin,
    WebhookDeliveryAdmin,
)
from vinta_django_questionnaires.admin.reporting import ResponseTable
from vinta_django_questionnaires.admin.responses import (
    AcknowledgedEditAdmin,
    MappingRunInline,
    QuestionnaireResponseAdmin,
    ReadOnlyAdmin,
    WebhookDeliveryInline,
)
from vinta_django_questionnaires.admin.structure import StructureEditor
from vinta_django_questionnaires.models import (
    AcknowledgedEdit,
    MappingRun,
    Page,
    Question,
    Questionnaire,
    QuestionnaireResponse,
    QuestionnaireVersion,
    QuestionnaireWidget,
    ResponseMapping,
    ResponseWebhook,
    Section,
    ValueSet,
    WebhookDelivery,
)

if TYPE_CHECKING:
    from django.db.models import Model

#: Set ``QUESTIONNAIRES_REGISTER_ADMIN = False`` to register these yourself.
REGISTER_SETTING = "QUESTIONNAIRES_REGISTER_ADMIN"

#: Every model this package exposes, and the admin it exposes it with.
REGISTRY: tuple[tuple[type[Model], type[admin.ModelAdmin]], ...] = (
    (Questionnaire, QuestionnaireAdmin),
    (QuestionnaireVersion, QuestionnaireVersionAdmin),
    (Page, PageAdmin),
    (Section, SectionAdmin),
    (Question, QuestionAdmin),
    (QuestionnaireWidget, QuestionnaireWidgetAdmin),
    (ValueSet, ValueSetAdmin),
    (QuestionnaireResponse, QuestionnaireResponseAdmin),
    (AcknowledgedEdit, AcknowledgedEditAdmin),
    (ResponseMapping, ResponseMappingAdmin),
    (ResponseWebhook, ResponseWebhookAdmin),
    (MappingRun, MappingRunAdmin),
    (WebhookDelivery, WebhookDeliveryAdmin),
)


def rebase(
    admin_class: type[admin.ModelAdmin],
    *,
    model_admin_base: Any = None,
    inline_base: Any = None,
) -> type[admin.ModelAdmin]:
    """*admin_class* with another base underneath it, inlines included.

    A themed admin -- django-unfold, say -- styles a form by way of the base
    class it is built on, so swapping the base is what it takes to make these
    look like the rest of the site.  The inlines need the same treatment, and
    they are declared inside the class, hence the rebuild.
    """
    if model_admin_base is None and inline_base is None:
        return admin_class
    attributes: dict[str, Any] = {}
    if inline_base is not None and getattr(admin_class, "inlines", None):
        attributes["inlines"] = [
            type(inline.__name__, (inline, inline_base), {}) for inline in admin_class.inlines
        ]
    bases = (admin_class, model_admin_base) if model_admin_base else (admin_class,)
    return type(admin_class.__name__, bases, attributes)


def register(
    site: admin.AdminSite | None = None,
    *,
    model_admin_base: Any = None,
    inline_base: Any = None,
    force: bool = False,
) -> None:
    """Register every model of this package against *site*.

    ``force`` re-registers over whatever is already there, which is what a
    project wants when it is replacing one of these rather than adding to it.
    """
    target = site or admin.site
    for model, admin_class in REGISTRY:
        if target.is_registered(model):
            if not force:
                continue
            target.unregister(model)
        target.register(
            model, rebase(admin_class, model_admin_base=model_admin_base, inline_base=inline_base)
        )


def unregister(site: admin.AdminSite | None = None) -> None:
    """Take every model of this package back off *site*."""
    target = site or admin.site
    for model, _admin_class in REGISTRY:
        if target.is_registered(model):
            target.unregister(model)


if getattr(settings, REGISTER_SETTING, True):
    register()


__all__ = [
    "REGISTRY",
    "AcknowledgedEditAdmin",
    "AcknowledgedEditAdminMixin",
    "AcknowledgedEditInlineMixin",
    "MappingRunAdmin",
    "MappingRunInline",
    "PageAdmin",
    "QuestionAdmin",
    "QuestionnaireAdmin",
    "QuestionnaireAssets",
    "QuestionnaireResponseAdmin",
    "QuestionnaireVersionAdmin",
    "QuestionnaireWidgetAdmin",
    "ReadOnlyAdmin",
    "ResponseMappingAdmin",
    "ResponseTable",
    "ResponseWebhookAdmin",
    "SectionAdmin",
    "StructureEditor",
    "ValueSetAdmin",
    "WebhookDeliveryAdmin",
    "WebhookDeliveryInline",
    "rebase",
    "register",
    "signed_form",
    "unregister",
]
