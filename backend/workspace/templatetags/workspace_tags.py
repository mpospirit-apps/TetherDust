from django import template
from django.urls import reverse

register = template.Library()


@register.simple_tag
def docs_content_url(source_id: object, file_path: object) -> str:
    """Build URL for docs_content_view, handling path argument."""
    return reverse(
        "workspace:docs_content", kwargs={"source_id": source_id, "file_path": file_path}
    )
