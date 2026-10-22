"""Aplica exclusivamente bases e projeções documentais; atualiza somente aferições [TESTE]."""
import hashlib
import json
from copy import deepcopy
from datetime import date
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.indicator_reference import test_values
from core.models import Indicator, QuarterlySectorReport
from core.pei_baseline_data import REFERENCE_PARAMETERS
from core.quarterly_reports import _snapshot


class Command(BaseCommand):
    help = 'Audita as linhas de base e projeções de DADOS INDICADORES.pdf. Use --apply para aplicar.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--update-tests', action='store_true')
        parser.add_argument('--refresh-reports', action='store_true')
        parser.add_argument('--year', type=int, default=2026)
        parser.add_argument('--audit-file')

    @transaction.atomic
    def handle(self, *args, **options):
        items = []
        for number, parameters in REFERENCE_PARAMETERS.items():
            matches = Indicator.objects.filter(code__in=[f'IE {number}', f'IR {number}'], artifacts__plan__acronym='PEI').distinct()
            if matches.count() != 1:
                raise CommandError(f'Indicador ausente ou ambíguo: {number}')
            items.append((matches.get(), parameters))
        audit = {'source': 'DADOS INDICADORES.pdf, páginas 46–50', 'applied': options['apply'],
                 'baseline_date_convention': '31/12/2024 representa o encerramento do ano-base 2024; o documento não informa dia de coleta.',
                 'indicators': [], 'updated_test_measurements': 0, 'refreshed_reports': 0}
        manifest_path = Path(settings.BASE_DIR) / '.test-data' / f'pei-{options["year"]}.json'
        manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else None
        for index, (indicator, parameters) in enumerate(items):
            audit['indicators'].append({'code': indicator.code, 'baseline_before': indicator.baseline,
                'reference_before': indicator.reference_parameters, 'reference': parameters})
            if not options['apply']:
                continue
            indicator.baseline = parameters['baseline_text']
            indicator.reference_parameters = deepcopy(parameters)
            indicator.save(update_fields=['baseline', 'reference_parameters'])
            if options['update_tests']:
                for measurement in indicator.measurements.filter(reference_period__startswith='[TESTE]', period_end__year=options['year']):
                    values = test_values(parameters, measurement.period_end, (Decimal('.55'), Decimal('.80'), Decimal('.95'), Decimal('1.10'))[index % 4])
                    if values is None:
                        continue
                    expected, result = values
                    measurement.baseline_value = parameters['baseline_text']
                    measurement.baseline_date = date(2024, 12, 31)
                    measurement.expected_value = expected
                    measurement.measured_value = str(result)
                    measurement.source_reference = f'[TESTE] Simulação com base em DADOS INDICADORES.pdf, p. {parameters["page"]}'
                    measurement.note = '[TESTE] Resultado fictício. Base e projeção extraídas do documento; 31/12/2024 é a referência anual convencionada, não uma data de coleta informada.'
                    if parameters['note']:
                        measurement.note += ' ' + parameters['note']
                    content = (f'[TESTE] AFERIÇÃO FICTÍCIA — SEM VALIDADE OFICIAL\n'
                               f'[TESTE] Indicador: {indicator.code}\n'
                               f'[TESTE] Período: {measurement.period_start} a {measurement.period_end}\n'
                               f'Base documental de 2024: {parameters["baseline_text"]} {parameters["unit"]}\n'
                               f'Fonte da base: DADOS INDICADORES.pdf, página {parameters["page"]}\n'
                               f'[TESTE] Planejado até o fim do período: {expected} {parameters["unit"]}\n'
                               f'[TESTE] Resultado simulado: {result} {parameters["unit"]}\n'
                               f'Observação: {parameters["note"]}\n').encode()
                    digest = hashlib.sha256(content).hexdigest()[:12]
                    filename = f'test_data/{options["year"]}/[TESTE]-base-documental-{measurement.pk}-{digest}.txt'
                    if not default_storage.exists(filename):
                        filename = default_storage.save(filename, ContentFile(content))
                    if manifest is not None and filename not in manifest['files']:
                        manifest['files'].append(filename)
                    measurement.evidence_attachment = filename
                    measurement.save(update_fields=['baseline_value', 'baseline_date', 'expected_value', 'measured_value', 'source_reference', 'note', 'evidence_attachment'])
                    audit['updated_test_measurements'] += 1
        if options['apply'] and options['refresh_reports']:
            for report in QuarterlySectorReport.objects.filter(plan__acronym='PEI'):
                previous = deepcopy(report.snapshot)
                history = previous.pop('previous_versions', [])
                if previous.get('reference_source') != audit['source']:
                    history.append({'snapshot': previous, 'reason': 'Atualização das bases e projeções documentais dos indicadores', 'replaced_at': timezone.now().isoformat()})
                snapshot = _snapshot(report.plan, report.unit, report.year, report.quarter)
                snapshot.update(previous_versions=history, reference_source=audit['source'],
                                last_edited_at=timezone.now().isoformat(), last_edited_by='revisão documental das linhas de base')
                if previous.get('test_batch'):
                    snapshot['test_batch'] = previous['test_batch']
                report.snapshot = snapshot
                report.save(update_fields=['snapshot'])
                audit['refreshed_reports'] += 1
        if options['apply'] and manifest is not None:
            manifest['reference_source'] = audit['source']
            temporary = manifest_path.with_suffix('.tmp')
            temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
            temporary.replace(manifest_path)
        if options['audit_file']:
            Path(options['audit_file']).write_text(json.dumps(audit, ensure_ascii=False, indent=2))
        self.stdout.write(self.style.SUCCESS(f'37 bases conferidas. Aferições [TESTE] atualizadas: {audit["updated_test_measurements"]}. Relatórios atualizados: {audit["refreshed_reports"]}. Aplicado: {options["apply"]}.'))
