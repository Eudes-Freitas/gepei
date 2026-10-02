from django.conf import settings
from django.db import models


class Organization(models.Model):
    name = models.CharField(max_length=180)
    acronym = models.CharField(max_length=30, blank=True)
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.acronym or self.name


class OrganizationalUnit(models.Model):
    class UnitType(models.TextChoices):
        ORGAN = "ORGAO", "Órgão"
        UNIT = "UNIDADE", "Unidade"
        SECTOR = "SETOR", "Setor"

    organization = models.ForeignKey(Organization, on_delete=models.PROTECT)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT)
    name = models.CharField(max_length=180)
    acronym = models.CharField(max_length=30, blank=True)
    unit_type = models.CharField(max_length=10, choices=UnitType.choices)

    def __str__(self):
        return self.acronym or self.name


class Plan(models.Model):
    class PlanType(models.TextChoices):
        PEI = "PEI", "PEI"
        PESP = "PESP", "PESP"
        PPA = "PPA", "PPA"
        OTHER = "OUTRO", "Outro"

    name = models.CharField(max_length=180)
    acronym = models.CharField(max_length=30)
    plan_type = models.CharField(max_length=10, choices=PlanType.choices)
    start_date = models.DateField()
    end_date = models.DateField()
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.acronym


class PlanArtifact(models.Model):
    class ArtifactType(models.TextChoices):
        DIMENSION = "DIMENSAO", "Dimensão BSC"
        AXIS = "EIXO", "Eixo Estratégico"
        OBJECTIVE = "OBJETIVO", "Objetivo Estratégico"
        PROJECT = "PROJETO", "Projeto Estratégico"

    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name="artifacts")
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE)
    artifact_type = models.CharField(max_length=12, choices=ArtifactType.choices)
    code = models.CharField(max_length=30, blank=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    def __str__(self):
        return f"{self.code} {self.title}".strip()


class StrategicAction(models.Model):
    class Status(models.TextChoices):
        NOT_STARTED = "NAO_INICIADA", "Não iniciada"
        IN_PROGRESS = "EM_ANDAMENTO", "Em andamento"
        COMPLETED = "CONCLUIDA", "Concluída"
        DELAYED = "ATRASADA", "Atrasada"
        BLOCKED = "BLOQUEADA", "Bloqueada"
        SUSPENDED = "SUSPENSA", "Suspensa"

    artifact = models.ForeignKey(PlanArtifact, on_delete=models.PROTECT, related_name="actions")
    coordinating_unit = models.ForeignKey(OrganizationalUnit, on_delete=models.PROTECT)
    code = models.CharField(max_length=30)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    due_date = models.DateField(
        null=True,
        blank=True,
        help_text="Preenchido no cronograma operacional; não é inferido da vigência do PEI.",
    )
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.NOT_STARTED)
    progress = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    funding_sources = models.CharField(max_length=255, blank=True)
    participating_units = models.ManyToManyField(OrganizationalUnit, related_name="participating_actions", blank=True)

    def __str__(self):
        return f"{self.code} — {self.title}"


class ActionPlan(models.Model):
    action = models.OneToOneField(StrategicAction, on_delete=models.CASCADE, related_name="action_plan")
    manager = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)


class Activity(models.Model):
    class FundingSource(models.TextChoices):
        FAF = "FAF", "Fundo a Fundo (FaF)"
        CODE_0500 = "0500", "Fonte 0500"
        AGREEMENT = "CONVENIO", "Convênio"
        OTHER = "OUTRA", "Outra"

    action_plan = models.ForeignKey(ActionPlan, on_delete=models.CASCADE, related_name="activities")
    executor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="assigned_activities")
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    position = models.PositiveIntegerField(default=0)
    weight = models.DecimalField(max_digits=5, decimal_places=2)
    progress = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField()
    status = models.CharField(max_length=15, choices=StrategicAction.Status.choices, default=StrategicAction.Status.NOT_STARTED)
    expected_delivery = models.CharField(max_length=255, blank=True)
    requires_financial_resource = models.BooleanField(default=False)
    planned_cost = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    disbursed_cost = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    funding_source = models.CharField(max_length=12, choices=FundingSource.choices, blank=True)
    funding_source_other = models.CharField(max_length=160, blank=True)
    financial_responsible_unit = models.ForeignKey(
        OrganizationalUnit,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="financially_monitored_activities",
    )
    financial_reference = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["position", "start_date", "end_date", "id"]

    def __str__(self):
        return self.title


class ActivityEvidence(models.Model):
    class EvidenceType(models.TextChoices):
        ATTACHMENT = "ANEXO", "Documento ou arquivo"
        LINK = "LINK", "Link"
        PHOTO = "FOTO", "Foto"
        SEI = "SEI", "Referência ao SEI"
        OTHER = "OUTRA", "Outra"

    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name="evidences")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    title = models.CharField(max_length=255)
    evidence_type = models.CharField(max_length=10, choices=EvidenceType.choices)
    description = models.TextField(blank=True)
    reference = models.CharField(max_length=255, blank=True)
    url = models.URLField(blank=True)
    attachment = models.FileField(upload_to="activity_evidences/%Y/%m/", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return self.title


class ActivityBlocker(models.Model):
    class Status(models.TextChoices):
        OPEN = "ABERTO", "Aberto"
        IN_TREATMENT = "EM_TRATAMENTO", "Em tratamento"
        RESOLVED = "RESOLVIDO", "Resolvido"

    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name="blockers")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="reported_activity_blockers",
    )
    resolution_owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="assigned_activity_blockers",
    )
    description = models.TextField()
    expected_resolution_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    resolution_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["status", "expected_resolution_date", "-created_at"]

    def __str__(self):
        return self.description[:80]


class StrategicTarget(models.Model):
    """Meta vinculada a objetivo, projeto ou ação estratégica."""

    artifact = models.ForeignKey(
        PlanArtifact,
        on_delete=models.PROTECT,
        related_name="targets",
    )
    action = models.ForeignKey(
        StrategicAction,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="targets",
    )
    code = models.CharField(max_length=30, blank=True)
    description = models.TextField()
    target_value = models.CharField(max_length=120, blank=True)
    unit_of_measure = models.CharField(max_length=80, blank=True)
    reference_period = models.CharField(max_length=120, blank=True)

    def __str__(self):
        return self.code or self.description[:60]


class Indicator(models.Model):
    class Direction(models.TextChoices):
        HIGHER_IS_BETTER = "MAIOR_MELHOR", "Maior é melhor"
        LOWER_IS_BETTER = "MENOR_MELHOR", "Menor é melhor"
        RANGE = "FAIXA", "Faixa esperada"

    class Frequency(models.TextChoices):
        MONTHLY = "MENSAL", "Mensal"
        BIMONTHLY = "BIMESTRAL", "Bimestral"
        QUARTERLY = "TRIMESTRAL", "Trimestral"
        FOUR_MONTHLY = "QUADRIMESTRAL", "Quadrimestral"
        SEMIANNUAL = "SEMESTRAL", "Semestral"
        ANNUAL = "ANUAL", "Anual"
        BIENNIAL = "BIENAL", "Bienal"
        OTHER = "OUTRA", "Outra"

    code = models.CharField(max_length=30, blank=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    formula = models.TextField(blank=True)
    unit_of_measure = models.CharField(max_length=80, blank=True)
    data_source = models.CharField(max_length=255, blank=True)
    frequency = models.CharField(max_length=16, choices=Frequency.choices, default=Frequency.ANNUAL)
    direction = models.CharField(max_length=16, choices=Direction.choices, default=Direction.HIGHER_IS_BETTER)
    baseline = models.CharField(max_length=120, blank=True)
    responsible_unit = models.ForeignKey(
        OrganizationalUnit,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="indicators",
    )
    artifacts = models.ManyToManyField(PlanArtifact, related_name="indicators", blank=True)
    targets = models.ManyToManyField(StrategicTarget, related_name="indicators", blank=True)

    def __str__(self):
        return f"{self.code} — {self.name}".strip(" —")


class IndicatorMeasurement(models.Model):
    indicator = models.ForeignKey(Indicator, on_delete=models.CASCADE, related_name="measurements")
    reference_period = models.CharField(max_length=120)
    measured_value = models.CharField(max_length=120)
    expected_value = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Meta prevista especificamente para o período desta aferição.",
    )
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    source_reference = models.CharField(max_length=255, blank=True)
    evidence_attachment = models.FileField(upload_to="indicator_measurements/%Y/%m/", blank=True)
    note = models.TextField(blank=True)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-recorded_at"]


class CriticalSuccessFactor(models.Model):
    artifact = models.ForeignKey(
        PlanArtifact,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="critical_success_factors",
    )
    action = models.ForeignKey(
        StrategicAction,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="critical_success_factors",
    )
    description = models.TextField()

    def __str__(self):
        return self.description[:60]


class ReportCycle(models.Model):
    class Status(models.TextChoices):
        OPEN = "ABERTO", "Aberto para preenchimento"
        CONSOLIDATING = "EM_CONSOLIDACAO", "Em consolidação"
        CLOSED = "ENCERRADO", "Encerrado"

    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="report_cycles")
    name = models.CharField(max_length=180)
    period_start = models.DateField()
    period_end = models.DateField()
    due_date = models.DateField()
    participating_units = models.ManyToManyField(OrganizationalUnit, related_name="report_cycles")
    status = models.CharField(max_length=18, choices=Status.choices, default=Status.OPEN)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_report_cycles")
    created_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-period_end", "-id"]

    def __str__(self):
        return self.name


class SectorReport(models.Model):
    class Status(models.TextChoices):
        DRAFT = "RASCUNHO", "Rascunho"
        SUBMITTED = "ENVIADO", "Enviado para validação"
        RETURNED = "DEVOLVIDO", "Devolvido para correção"
        APPROVED = "APROVADO", "Aprovado"
        CONSOLIDATED = "CONSOLIDADO", "Consolidado"

    cycle = models.ForeignKey(ReportCycle, on_delete=models.CASCADE, related_name="sector_reports")
    unit = models.ForeignKey(OrganizationalUnit, on_delete=models.PROTECT, related_name="sector_reports")
    prepared_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="prepared_sector_reports",
    )
    validator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="assigned_sector_reports",
    )
    status = models.CharField(max_length=14, choices=Status.choices, default=Status.DRAFT)
    executive_summary = models.TextField(blank=True)
    complements = models.TextField(blank=True)
    next_steps = models.TextField(blank=True)
    management_decision_needed = models.TextField(blank=True)
    validator_comment = models.TextField(blank=True)
    resubmission_due_date = models.DateField(null=True, blank=True)
    snapshot = models.JSONField(default=dict, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    validated_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["cycle", "unit"], name="unique_report_per_cycle_unit")]
        ordering = ["unit__name"]

    def __str__(self):
        return f"{self.cycle} · {self.unit}"


class Risk(models.Model):
    class Status(models.TextChoices):
        IDENTIFIED = "IDENTIFICADO", "Identificado"
        IN_TREATMENT = "EM_TRATAMENTO", "Em tratamento"
        MONITORING = "EM_MONITORAMENTO", "Em monitoramento"
        MATERIALIZED = "MATERIALIZADO", "Materializado"
        CLOSED = "ENCERRADO", "Encerrado"

    class OccurrenceTiming(models.TextChoices):
        ANY_TIME = "QUALQUER_MOMENTO", "Pode ocorrer a qualquer momento"
        EXPOSURE_WINDOW = "PERIODO", "Durante um período de exposição"
        DATE_OR_MILESTONE = "DATA_MARCO", "Em uma data ou marco provável"
        UNKNOWN = "INDETERMINADO", "Não é possível estimar o momento"

    action = models.ForeignKey(StrategicAction, on_delete=models.CASCADE, related_name="risks")
    activity = models.ForeignKey(Activity, null=True, blank=True, on_delete=models.SET_NULL, related_name="risks")
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    title = models.CharField(max_length=255)
    cause = models.TextField()
    probability = models.PositiveSmallIntegerField()
    impact = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.IDENTIFIED)
    treatment = models.CharField(max_length=20, blank=True)
    preventive_measure = models.TextField(blank=True)
    contingency_measure = models.TextField(blank=True)
    occurrence_timing = models.CharField(
        max_length=20,
        choices=OccurrenceTiming.choices,
        default=OccurrenceTiming.UNKNOWN,
    )
    exposure_start_date = models.DateField(null=True, blank=True)
    exposure_end_date = models.DateField(null=True, blank=True)
    expected_occurrence_date = models.DateField(null=True, blank=True)
    trigger_description = models.TextField(blank=True)

    @property
    def level(self):
        return self.probability * self.impact

    @property
    def level_label(self):
        if self.level >= 20:
            return "Crítico"
        if self.level >= 15:
            return "Muito alto"
        if self.level >= 10:
            return "Alto"
        if self.level >= 5:
            return "Moderado"
        return "Baixo"

    @property
    def occurrence_timing_summary(self):
        if self.occurrence_timing == self.OccurrenceTiming.ANY_TIME:
            return "Pode ocorrer a qualquer momento"
        if self.occurrence_timing == self.OccurrenceTiming.EXPOSURE_WINDOW:
            if self.exposure_start_date and self.exposure_end_date:
                return f"De {self.exposure_start_date:%d/%m/%Y} a {self.exposure_end_date:%d/%m/%Y}"
            if self.exposure_start_date:
                return f"A partir de {self.exposure_start_date:%d/%m/%Y}"
            if self.exposure_end_date:
                return f"Até {self.exposure_end_date:%d/%m/%Y}"
            return "Durante um período de exposição ainda não delimitado"
        if self.occurrence_timing == self.OccurrenceTiming.DATE_OR_MILESTONE:
            if self.expected_occurrence_date:
                return f"Data provável: {self.expected_occurrence_date:%d/%m/%Y}"
            return "Associado a um marco ou condição"
        return "Momento indeterminado"


class RiskAssessment(models.Model):
    class AssessmentType(models.TextChoices):
        CURRENT = "ATUAL", "Avaliação atual"
        INHERENT = "INERENTE", "Risco inerente"
        RESIDUAL = "RESIDUAL", "Risco residual"

    risk = models.ForeignKey(Risk, on_delete=models.CASCADE, related_name="assessments")
    assessment_type = models.CharField(max_length=10, choices=AssessmentType.choices, default=AssessmentType.CURRENT)
    probability = models.PositiveSmallIntegerField()
    impact = models.PositiveSmallIntegerField()
    notes = models.TextField(blank=True)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    assessed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-assessed_at", "-id"]

    @property
    def level(self):
        return self.probability * self.impact


class RiskTreatment(models.Model):
    class Decision(models.TextChoices):
        ACCEPT = "ACEITAR", "Aceitar"
        MITIGATE = "MITIGAR", "Mitigar"
        AVOID = "EVITAR", "Evitar"
        TRANSFER = "TRANSFERIR", "Transferir"

    risk = models.ForeignKey(Risk, on_delete=models.CASCADE, related_name="treatments")
    decision = models.CharField(max_length=12, choices=Decision.choices)
    justification = models.TextField(blank=True)
    responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="risk_treatments",
    )
    due_date = models.DateField(null=True, blank=True)
    preventive_measure = models.TextField(blank=True)
    contingency_measure = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_risk_treatments",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class RiskMaterialization(models.Model):
    risk = models.ForeignKey(Risk, on_delete=models.CASCADE, related_name="materializations")
    occurred_on = models.DateField()
    description = models.TextField()
    actual_impact = models.TextField()
    actions_taken = models.TextField()
    evidence_reference = models.CharField(max_length=255, blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-occurred_on", "-id"]


class RiskAcceptance(models.Model):
    class Decision(models.TextChoices):
        ACCEPTED = "ACEITO", "Aceito"
        ACCEPTED_WITH_RESERVATIONS = "ACEITO_RESSALVAS", "Aceito com ressalvas"
        NOT_ACCEPTED = "NAO_ACEITO", "Não aceito"

    risk = models.ForeignKey(Risk, on_delete=models.CASCADE, related_name="acceptances")
    authority = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="risk_acceptances",
    )
    decision = models.CharField(max_length=20, choices=Decision.choices)
    justification = models.TextField()
    remedial_actions = models.TextField(blank=True)
    remediation_responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="assigned_risk_remediations",
    )
    reevaluation_due_date = models.DateField(null=True, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="recorded_risk_acceptances",
    )
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-recorded_at", "-id"]


class RiskRemediationSubmission(models.Model):
    acceptance = models.ForeignKey(
        RiskAcceptance,
        on_delete=models.CASCADE,
        related_name="remediation_submissions",
    )
    completion_summary = models.TextField()
    evidence_reference = models.CharField(max_length=255, blank=True)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="submitted_risk_remediations",
    )
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-submitted_at", "-id"]
