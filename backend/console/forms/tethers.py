"""Forms for tether configuration."""

from typing import cast

from core.forms.base import _BaseForm
from core.models import Codebase, DocumentationSource, Role, Tether
from django import forms
from django.forms import ModelChoiceField


class TetherForm(_BaseForm):
    allowed_roles = forms.ModelMultipleChoiceField(
        queryset=Role.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Allowed Roles",
        help_text="Roles that can view this tether",
    )

    class Meta:
        model = Tether
        fields = [
            "name",
            "description",
            "codebase",
            "database_doc_source",
            "allowed_roles",
            "is_active",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        cast(
            ModelChoiceField[Codebase], self.fields["codebase"]
        ).queryset = Codebase.objects.filter(is_active=True)
        cast(
            ModelChoiceField[DocumentationSource], self.fields["database_doc_source"]
        ).queryset = DocumentationSource.objects.filter(
            doc_type=DocumentationSource.DocType.DATABASE,
            is_active=True,
        )
