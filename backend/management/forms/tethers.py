"""Forms for tether configuration."""

from typing import Any, cast

from django import forms
from django.forms import ModelChoiceField
from engine.forms.base import _BaseForm
from engine.models import Codebase, DocumentationSource, Role, Tether

# Prefixes that encode the source type in the combined dropdown value.
_CODEBASE_PREFIX = "codebase"
_CODEBASE_DOC_PREFIX = "codebasedoc"


class TetherForm(_BaseForm):
    code_source = forms.ChoiceField(
        label="Codebase or Codebase Documentation",
        help_text=(
            "The code side of this tether — a live codebase repository or a codebase "
            "documentation source."
        ),
        widget=forms.Select,
    )
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
            "code_source",
            "database_doc_source",
            "allowed_roles",
            "is_active",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)

        codebases = Codebase.objects.filter(is_active=True)
        codebase_docs = DocumentationSource.objects.filter(
            doc_type=DocumentationSource.DocType.CODEBASE,
            is_active=True,
        )
        choices: list[Any] = [("", "— Select a code source —")]
        if codebases:
            choices.append(
                (
                    "Codebases",
                    [(f"{_CODEBASE_PREFIX}:{c.pk}", c.name) for c in codebases],
                )
            )
        if codebase_docs:
            choices.append(
                (
                    "Codebase Documentation",
                    [(f"{_CODEBASE_DOC_PREFIX}:{d.pk}", d.folder_name) for d in codebase_docs],
                )
            )
        cast(forms.ChoiceField, self.fields["code_source"]).choices = choices

        # Pre-select the existing source when editing.
        if self.instance and self.instance.pk:
            if self.instance.codebase_id:
                self.initial["code_source"] = f"{_CODEBASE_PREFIX}:{self.instance.codebase_id}"
            elif self.instance.codebase_doc_source_id:
                self.initial["code_source"] = (
                    f"{_CODEBASE_DOC_PREFIX}:{self.instance.codebase_doc_source_id}"
                )

        cast(
            ModelChoiceField[DocumentationSource], self.fields["database_doc_source"]
        ).queryset = DocumentationSource.objects.filter(
            doc_type=DocumentationSource.DocType.DATABASE,
            is_active=True,
        )

    def clean_code_source(self) -> tuple[str, Any]:
        """Resolve the combined value into (kind, model instance)."""
        value = self.cleaned_data.get("code_source")
        if not value:
            raise forms.ValidationError("Select a codebase or codebase documentation source.")
        kind, _, pk = value.partition(":")
        if kind == _CODEBASE_PREFIX:
            codebase_obj = Codebase.objects.filter(pk=pk, is_active=True).first()
            if codebase_obj is None:
                raise forms.ValidationError("Selected codebase is no longer available.")
            return (_CODEBASE_PREFIX, codebase_obj)
        if kind == _CODEBASE_DOC_PREFIX:
            doc_obj = DocumentationSource.objects.filter(
                pk=pk, doc_type=DocumentationSource.DocType.CODEBASE, is_active=True
            ).first()
            if doc_obj is None:
                raise forms.ValidationError(
                    "Selected codebase documentation is no longer available."
                )
            return (_CODEBASE_DOC_PREFIX, doc_obj)
        raise forms.ValidationError("Invalid code source.")

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean()
        if cleaned is None:
            cleaned = {}
        source = cleaned.get("code_source")
        # Assign onto the instance before model validation (_post_clean) so
        # Tether.clean()'s "exactly one code source" check sees the FKs set.
        if source:
            kind, obj = source
            if kind == _CODEBASE_PREFIX:
                self.instance.codebase = obj
                self.instance.codebase_doc_source = None
            else:
                self.instance.codebase = None
                self.instance.codebase_doc_source = obj
        return cleaned
