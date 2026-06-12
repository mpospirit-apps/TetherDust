"""Shared base classes for chat forms."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django import forms

if TYPE_CHECKING:
    _Base = forms.ModelForm[Any]
else:
    _Base = forms.ModelForm


class _BaseForm(_Base):
    """Mixin that adds form-control CSS class to all standard widgets."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        skip = (forms.CheckboxInput, forms.CheckboxSelectMultiple, forms.RadioSelect)
        for field in self.fields.values():
            if not isinstance(field.widget, skip):
                field.widget.attrs.setdefault("class", "form-control")
