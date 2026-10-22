"""Varia somente as atividades identificadas no manifesto da carga [TESTE]."""
import json
from copy import deepcopy
from decimal import Decimal, ROUND_DOWN
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.models import Activity, QuarterlySectorReport, StrategicAction
from core.quarterly_reports import _snapshot
from core.views import _sync_action_progress


class Command(BaseCommand):
    help = 'Varia as quantidades e a execução das atividades [TESTE], preservando os cadastros originais.'

    def add_arguments(self, parser):
        parser.add_argument('--year', type=int, default=timezone.localdate().year)

    @transaction.atomic
    def handle(self, *args, **options):
        path = Path(settings.BASE_DIR) / '.test-data' / f'pei-{options["year"]}.json'
        if not path.exists():
            raise CommandError('Carregue os dados [TESTE] antes de variar sua execução.')
        manifest = json.loads(path.read_text())
        ids = manifest['records']['activities']
        actions = StrategicAction.objects.filter(action_plan__activities__pk__in=ids).distinct().order_by('code')
        distribution = []
        for index, action in enumerate(actions):
            plan = action.action_plan
            existing = list(plan.activities.filter(pk__in=ids).order_by('position', 'pk'))
            if len(existing) < 3:
                raise CommandError(f'{action.code}: cenário de teste incompleto.')
            # Keep the three base activities: evidence and risk links remain valid.
            base = existing[:3]
            desired_count = 3 + index % 6
            extras = existing[3:]
            while len(base) + len(extras) < desired_count:
                number = len(extras) + 1
                activity = Activity.objects.create(
                    action_plan=plan, executor=base[0].executor,
                    title=f'{manifest["batch"]} {action.code} — Entrega complementar {number}',
                    description='[TESTE] Entrega simulada para variar a quantidade de atividades.',
                    expected_delivery='[TESTE] Produto fictício para validar a execução.',
                    weight=0, progress=1, status='EM_ANDAMENTO', position=103 + number,
                    start_date=base[0].start_date, end_date=base[0].end_date,
                )
                extras.append(activity)
                ids.append(activity.pk)
            removed = extras[max(0, desired_count - 3):]
            for activity in removed:
                if activity.risks.exists() or activity.evidences.exists() or activity.blockers.exists():
                    raise CommandError(f'A atividade {activity.pk} recebeu registros adicionais e não pode ser removida nesta variação.')
                removed_id = activity.pk
                activity.delete()
                ids.remove(removed_id)
            group = base + extras[:desired_count - 3]
            original_weight = sum((a.weight for a in plan.activities.exclude(pk__in=ids)), Decimal('0'))
            available = max(Decimal('0'), Decimal('100') - original_weight)
            first_weight = (available * Decimal('.02')).quantize(Decimal('.01'), rounding=ROUND_DOWN)
            other_weight = ((available - first_weight) / (len(group) - 1)).quantize(Decimal('.01'), rounding=ROUND_DOWN)
            goal = Decimal([5, 15, 25, 35, 45, 55, 65, 75, 85, 95, 100][index % 11])
            other_progress = ((goal - 2) / Decimal('.98')).quantize(Decimal('.01'))
            assigned = Decimal('0')
            for number, activity in enumerate(group):
                activity.weight = first_weight if number == 0 else available - assigned if number == len(group) - 1 else other_weight
                assigned += activity.weight
                activity.progress = Decimal('100') if number == 0 or goal == 100 else other_progress
                activity.status = 'CONCLUIDA' if activity.progress == 100 else 'EM_ANDAMENTO'
                activity.save(update_fields=['weight', 'progress', 'status'])
            _sync_action_progress(action, plan)
            distribution.append({'action': action.code, 'test_activities': len(group), 'progress': str(action.progress)})
        for report in QuarterlySectorReport.objects.filter(plan__acronym='PEI', year=options['year']):
            previous = deepcopy(report.snapshot)
            history = previous.pop('previous_versions', [])
            if previous.get('test_batch') != manifest['batch']:
                history.append({'snapshot': previous, 'reason': '[TESTE] Variação autorizada da execução', 'replaced_at': timezone.now().isoformat()})
            snapshot = _snapshot(report.plan, report.unit, report.year, report.quarter)
            snapshot.update(previous_versions=history, test_batch=manifest['batch'], contains_test_data=True)
            report.snapshot = snapshot
            report.save(update_fields=['snapshot'])
        manifest['varied_activities'] = True
        manifest['activity_distribution'] = distribution
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
        temporary.replace(path)
        self.stdout.write(self.style.SUCCESS(f'{len(distribution)} ações: 3 a 8 atividades [TESTE] por ação, com execução variada. Relatórios atualizados.'))
