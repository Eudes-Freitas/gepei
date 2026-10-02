from django import template
from django.utils.html import format_html

register = template.Library()


@register.simple_tag
def progress_bar(value, css_class="progress-track"):
    """Barra de execução colorida pela conclusão: vermelho, laranja e verde."""
    try:
        percent = min(max(float(value or 0), 0), 100)
    except (TypeError, ValueError):
        percent = 0
    if percent < 34:
        level = "progress-low"
    elif percent < 67:
        level = "progress-mid"
    else:
        level = "progress-high"
    # Largura sempre com ponto decimal: com pt-BR o Django geraria "0,6%", que o CSS ignora.
    return format_html(
        '<div class="{} {}" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="{}">'
        '<i style="width: {}%"></i></div>',
        css_class,
        level,
        f"{percent:.1f}",
        f"{percent:.2f}",
    )
