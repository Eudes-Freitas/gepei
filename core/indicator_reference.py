"""Comparação com as projeções documentais, sem substituir as metas originais."""
from datetime import date
from decimal import Decimal, InvalidOperation


def number(value):
    text = str(value).strip().replace("%", "").replace(" ", "")
    if "," in text and "." in text:
        text = text.replace(".", "")
    try:
        return Decimal(text.replace(",", "."))
    except InvalidOperation:
        return None


def expected_at(parameters, when, aggregate=False):
    projections = parameters['projections']
    mode = parameters['mode']
    if mode in ('annual', 'threshold'):
        value = projections.get(str(when.year))
        if mode == 'threshold':
            return Decimal(value) if value is not None else None
        total = sum((Decimal(v) for y, v in projections.items() if int(y) < when.year and v is not None), Decimal('0')) if aggregate else Decimal('0')
        if value is None:
            return total if aggregate else None
        start, end = date(when.year - 1, 12, 31), date(when.year, 12, 31)
        return total + Decimal(value) * Decimal((when - start).days) / Decimal((end - start).days)
    base = parameters['baseline_value']
    points = [(date(2024, 12, 31), Decimal(base) if base is not None else Decimal('0'))]
    points.extend((date(int(y), 12, 31), Decimal(v)) for y, v in projections.items() if v is not None)
    if when <= points[0][0]:
        return points[0][1]
    for (start, low), (end, high) in zip(points, points[1:]):
        if when <= end:
            return low + (high - low) * Decimal((when - start).days) / Decimal((end - start).days)
    return points[-1][1]


def document_pace(indicator, measurement, measurements, when, aggregate=False):
    parameters = indicator.reference_parameters
    expected = expected_at(parameters, when, aggregate=aggregate)
    if expected is None:
        return {'code': 'gray', 'label': 'Sem previsão documental no período', 'achievement': None}
    measured = number(measurement.measured_value)
    base = Decimal(parameters['baseline_value']) if parameters['baseline_value'] is not None else Decimal('0')
    if parameters['mode'] == 'annual':
        base = Decimal('0')
        if aggregate:
            by_year = {}
            for item in measurements:
                if item.period_end and item.period_end <= when and number(item.measured_value) is not None:
                    previous = by_year.get(item.period_end.year)
                    if previous is None or (item.period_end, item.recorded_at, item.pk) > (previous.period_end, previous.recorded_at, previous.pk):
                        by_year[item.period_end.year] = item
            measured = sum((number(item.measured_value) for item in by_year.values()), Decimal('0'))
    if parameters['mode'] == 'threshold':
        achievement = measured / expected * 100 if expected else Decimal('100')
    elif expected == base:
        return {'code': 'gray', 'label': 'Período não iniciado', 'achievement': None}
    else:
        achievement = max(Decimal('0'), (measured - base) / (expected - base) * 100)
    if parameters.get('strict') and (parameters["mode"] == "threshold" or when.year == max(map(int, parameters["projections"]))) and measured == expected and achievement >= 100:
        achievement = Decimal('99.9')
    return {'calculation_mode': 'document', 'achievement': achievement,
            'evaluation_date': when, 'expected_value': expected,
            'reference_unit': parameters['unit'], 'source': parameters['source'],
            'realized_value': measured, 'reference_baseline': parameters['baseline_text']}


def test_values(parameters, when, ratio):
    expected = expected_at(parameters, when)
    if expected is None:
        return None
    base = Decimal(parameters['baseline_value']) if parameters['baseline_value'] is not None else Decimal('0')
    if parameters['mode'] in ('annual', 'threshold'):
        base = Decimal('0')
    result = (base + (expected - base) * ratio).quantize(Decimal('.001'))
    if parameters['unit'].startswith('%'):
        result = min(Decimal('100'), result)
    if parameters['unit'] in ('servidores', 'iniciativas', 'ações', 'soluções', 'processos', 'publicações', 'parcerias', 'projetos', 'operações'):
        result = result.quantize(Decimal('1'))
    return expected.quantize(Decimal('.01')), result
