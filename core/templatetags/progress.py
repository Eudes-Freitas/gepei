import math

from django import template
from django.utils.html import format_html

register = template.Library()


def progress_color(percent):
    stops = [(0, (211, 47, 47)), (25, (244, 124, 72)), (50, (255, 209, 102)),
             (75, (168, 216, 135)), (100, (25, 135, 84))]
    for (start, low), (end, high) in zip(stops, stops[1:]):
        if percent <= end:
            ratio = (percent - start) / (end - start)
            return "#{:02x}{:02x}{:02x}".format(*(round(a + (b - a) * ratio) for a, b in zip(low, high)))
    return "#198754"


@register.simple_tag
def progress_bar(value, css_class="progress-track"):
    """Barra de execução colorida pela conclusão: vermelho, laranja e verde."""
    try:
        percent = float(value or 0)
        percent = min(max(percent, 0), 100) if math.isfinite(percent) else 0
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
        '<div class="{} {}" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="{}" style="--progress-color: {}">'
        '<i style="width: {}%"></i></div>',
        css_class,
        level,
        f"{percent:.1f}",
        progress_color(percent),
        f"{percent:.2f}",
    )
