"""Carga rastreável e removível de dados fictícios, sem alterar o cadastro do PEI."""
import json
from copy import deepcopy
from datetime import datetime, time
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from core.models import (ActionPlan, Activity, ActivityBlocker, ActivityEvidence,
                         Indicator, IndicatorMeasurement, Plan, QuarterlySectorReport,
                         Risk, RiskAssessment, RiskTreatment, StrategicAction)
from core.quarterly_reports import _period, _snapshot


class Command(BaseCommand):
    help = 'Preenche o PEI com registros [TESTE]. Use --remove para remover somente esta carga.'

    def add_arguments(self, parser):
        parser.add_argument('--year', type=int, default=timezone.localdate().year)
        parser.add_argument('--remove', action='store_true')

    def handle(self, *args, **options):
        year = options['year']
        if not 2000 <= year <= 2100:
            raise CommandError('Informe um ano entre 2000 e 2100.')
        path = Path(settings.BASE_DIR) / '.test-data' / f'pei-{year}.json'
        manifest = json.loads(path.read_text()) if path.exists() else {
            'batch': f'[TESTE] PEI {year}', 'year': year, 'records': {},
            'files': [], 'original_reports': {}, 'original_actions': {},
        }
        if options['remove']:
            if not path.exists():
                raise CommandError('Não existe manifesto desta carga para remover com segurança.')
            self.remove(manifest)
            path.unlink()
            self.stdout.write(self.style.SUCCESS('Carga [TESTE] removida; relatórios anteriores restaurados.'))
            return
        created_files = []
        try:
            with transaction.atomic():
                self.populate(manifest, created_files)
                path.parent.mkdir(parents=True, exist_ok=True)
                temporary = path.with_suffix('.tmp')
                temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
                temporary.replace(path)
                if Indicator.objects.exclude(reference_parameters={}).filter(artifacts__plan__acronym="PEI").exists():
                    from django.core.management import call_command
                    call_command("load_indicator_reference", apply=True, update_tests=True, refresh_reports=True,
                                 year=year, stdout=self.stdout)
        except Exception:
            for filename in created_files:
                default_storage.delete(filename)
            raise
        counts = {name: len(ids) for name, ids in manifest['records'].items()}
        self.stdout.write(self.style.SUCCESS(json.dumps(counts, ensure_ascii=False)))
        self.stdout.write(f'Manifesto: {path}\nRemover: python manage.py load_test_execution --year {year} --remove')

    def track(self, manifest, name, instance, created):
        if created:
            ids = manifest['records'].setdefault(name, [])
            if instance.pk not in ids:
                ids.append(instance.pk)
        return instance

    def file(self, manifest, created_files, key, content):
        filename = f'test_data/{manifest["year"]}/[TESTE]-{key}.txt'
        if not default_storage.exists(filename):
            filename = default_storage.save(filename, ContentFile(('[TESTE] DADOS FICTÍCIOS — SEM VALIDADE OFICIAL\n\n' + content).encode()))
            created_files.append(filename)
        if filename not in manifest['files']:
            manifest['files'].append(filename)
        return filename

    def populate(self, manifest, created_files):
        from core.views import _decimal_from_measurement
        year = manifest['year']
        batch = manifest['batch']
        plan = Plan.objects.get(acronym='PEI')
        user = get_user_model().objects.filter(is_active=True).exclude(username__startswith="[TESTE]").order_by("-is_superuser", "pk").first()
        if not user:
            raise CommandError("É necessário um usuário existente para registrar os dados de teste.")
        actions = list(StrategicAction.objects.filter(artifact__plan=plan).select_related('coordinating_unit').order_by('code'))
        for index, action in enumerate(actions):
            action_plan, created = ActionPlan.objects.get_or_create(action=action, defaults={'manager': user})
            self.track(manifest, 'plans', action_plan, created)
            existing_weight = action_plan.activities.exclude(title__startswith=batch).aggregate(total=Sum('weight'))['total'] or Decimal('0')
            available = max(Decimal('0'), Decimal('100') - existing_weight)
            weight = (available / 4).quantize(Decimal('.01'), rounding='ROUND_DOWN')
            activities = []
            for number, (label, progress, status) in enumerate([
                ('Entrega concluída', 100, 'CONCLUIDA'), ('Entrega em execução', 50, 'EM_ANDAMENTO'),
                ('Entrega parcial', 25, 'EM_ANDAMENTO'), ('Entrega em execução complementar', 40, 'EM_ANDAMENTO'),
            ]):
                if manifest.get("varied_activities") and number == 3:
                    continue
                activity, created = Activity.objects.get_or_create(action_plan=action_plan, title=f'{batch} {action.code} — {label}', defaults={
                    'executor': user, 'description': '[TESTE] Cenário fictício para validar execução e relatórios.',
                    'expected_delivery': '[TESTE] Produto simulado, sem validade oficial.',
                    'weight': weight if number < 3 else available - weight * 3,
                    'progress': progress, 'status': status, 'position': 100 + number,
                    'start_date': _period(year, 1)[0], 'end_date': _period(year, 4)[1],
                    'requires_financial_resource': number < 3, 'planned_cost': Decimal('1000') * (index + 1) if number < 3 else None,
                    'disbursed_cost': Decimal('1000') * (index + 1) * Decimal(progress) / 100 if number < 3 else None,
                    'funding_source': '0500' if number < 3 else '', 'financial_responsible_unit': action.coordinating_unit,
                    'financial_reference': '[TESTE] Dotação fictícia para conferência.',
                })
                self.track(manifest, 'activities', activity, created)
                activities.append(activity)
            for quarter in range(1, 5):
                start, end = _period(year, quarter)
                evidence, created = ActivityEvidence.objects.get_or_create(activity=activities[0], title=f'{batch} {quarter}º trimestre — Evidência de {action.code}', defaults={
                    'created_by': user, 'evidence_type': 'ANEXO', 'description': '[TESTE] Comprovação fictícia da entrega simulada.',
                    'reference': f'[TESTE] Documento {action.code}/{year}/T{quarter}',
                    'attachment': self.file(manifest, created_files, f'atividade-{action.pk}-T{quarter}', f'[TESTE] Ação: {action.code}\n[TESTE] Atividade: {activities[0].title}\n[TESTE] Período: {start} a {end}\n[TESTE] Execução simulada: 100%.\n'),
                })
                self.track(manifest, 'evidences', evidence, created)
                if created:
                    ActivityEvidence.objects.filter(pk=evidence.pk).update(created_at=timezone.make_aware(datetime.combine(end, time(12))))
            risk, created = Risk.objects.get_or_create(action=action, title=f'{batch} Atraso simulado de {action.code}', defaults={
                'activity': activities[1], 'owner': user, 'cause': '[TESTE] Possível atraso na disponibilidade dos dados.',
                'probability': 1 + index % 5, 'impact': 1 + (index // 5) % 5, 'status': Risk.Status.IN_TREATMENT,
                'occurrence_timing': Risk.OccurrenceTiming.ANY_TIME, 'treatment': 'MITIGAR',
                'preventive_measure': '[TESTE] Acompanhamento semanal simulado.', 'contingency_measure': '[TESTE] Reprogramar entrega simulada.',
            })
            self.track(manifest, 'risks', risk, created)
            assessment, created = RiskAssessment.objects.get_or_create(risk=risk, notes=f'{batch} Avaliação fictícia', defaults={
                'probability': risk.probability, 'impact': risk.impact, 'author': user,
            })
            self.track(manifest, 'assessments', assessment, created)
            treatment, created = RiskTreatment.objects.get_or_create(risk=risk, defaults={
                'decision': 'MITIGAR', 'responsible': user, 'created_by': user, 'due_date': _period(year, 4)[1],
                'justification': '[TESTE] Resposta fictícia ao risco.', 'preventive_measure': '[TESTE] Conferir dados simulados semanalmente.',
                'contingency_measure': '[TESTE] Reprogramar o cronograma fictício.',
            })
            self.track(manifest, 'treatments', treatment, created)
        indicators = Indicator.objects.filter(Q(artifacts__plan=plan) | Q(targets__artifact__plan=plan)).distinct().prefetch_related('targets')
        for index, indicator in enumerate(indicators):
            target = next(iter(indicator.targets.all()), None)
            final = _decimal_from_measurement(target.target_value) if target else None
            if final is None or final <= 0:
                final = Decimal('100')
            for quarter in range(1, 5):
                start, end = _period(year, quarter)
                expected = (final * Decimal(quarter) / 4).quantize(Decimal('.01'))
                ratio = (Decimal('.45'), Decimal('.70'), Decimal('.90'), Decimal('1.05'))[(index + quarter - 1) % 4]
                if indicator.direction == Indicator.Direction.LOWER_IS_BETTER:
                    ratio = 2 - ratio
                result = (expected * ratio).quantize(Decimal('.01'))
                measurement, created = IndicatorMeasurement.objects.get_or_create(indicator=indicator, reference_period=f'[TESTE] {quarter}º trimestre de {year}', defaults={
                    'baseline_value': '0', 'baseline_date': _period(year, 1)[0], 'period_start': start, 'period_end': end,
                    'measured_value': str(result), 'expected_value': expected, 'recorded_by': user, 'measured_by': user,
                    'measured_unit': indicator.responsible_unit, 'source_reference': f'{batch} Base fictícia de {indicator.code}',
                    'note': '[TESTE] Valores simulados; não representam desempenho real.',
                    'evidence_attachment': self.file(manifest, created_files, f'indicador-{indicator.pk}-T{quarter}', f'[TESTE] Indicador: {indicator.code}\n[TESTE] Período: {start} a {end}\n[TESTE] Planejado no trimestre: {expected}\n[TESTE] Aferido: {result}\n[TESTE] Unidade: {indicator.unit_of_measure}\n'),
                })
                self.track(manifest, 'measurements', measurement, created)
        unit_ids = {a.coordinating_unit_id for a in actions}
        for action in actions:
            unit_ids.update(action.participating_units.values_list('pk', flat=True))
        from core.models import OrganizationalUnit
        for unit in OrganizationalUnit.objects.filter(pk__in=unit_ids):
            for quarter in range(1, 5):
                report, created = QuarterlySectorReport.objects.get_or_create(plan=plan, unit=unit, year=year, quarter=quarter, defaults={'consolidated_by': user, 'snapshot': {}})
                self.track(manifest, 'reports', report, created)
                if not created and report.pk not in manifest['records'].get('reports', []):
                    manifest['original_reports'].setdefault(str(report.pk), deepcopy(report.snapshot))
                snapshot = _snapshot(plan, unit, year, quarter)
                previous = deepcopy(report.snapshot)
                history = previous.pop('previous_versions', [])
                if previous and previous.get('test_batch') != batch:
                    history.append({'snapshot': previous, 'reason': f'{batch} Inclusão autorizada de cenários fictícios', 'replaced_at': timezone.now().isoformat()})
                snapshot.update(previous_versions=history, test_batch=batch, contains_test_data=True)
                report.snapshot = snapshot
                report.save(update_fields=['snapshot'])

    @transaction.atomic
    def remove(self, manifest):
        from django.apps import apps
        model_names = {'reports': 'QuarterlySectorReport', 'measurements': 'IndicatorMeasurement',
            'treatments': 'RiskTreatment', 'assessments': 'RiskAssessment', 'risks': 'Risk',
            'blockers': 'ActivityBlocker', 'evidences': 'ActivityEvidence', 'activities': 'Activity'}
        for name, model in model_names.items():
            apps.get_model('core', model).objects.filter(pk__in=manifest['records'].get(name, [])).delete()
        for pk, snapshot in manifest['original_reports'].items():
            QuarterlySectorReport.objects.filter(pk=pk).update(snapshot=snapshot)
        ActionPlan.objects.filter(pk__in=manifest['records'].get('plans', []), activities__isnull=True).delete()
        # The user is deliberately retained if any record created later still references it.
        from django.db.models.deletion import ProtectedError
        for user in get_user_model().objects.filter(pk__in=manifest['records'].get('users', [])):
            try:
                with transaction.atomic():
                    user.delete()
            except ProtectedError:
                pass
        transaction.on_commit(lambda: [default_storage.delete(name) for name in manifest['files']])
