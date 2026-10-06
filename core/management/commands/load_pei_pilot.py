"""Carga inicial, idempotente e auditável do recorte SRH do PEI 2025-2034."""

from datetime import date

from django.core.management import call_command
from django.core.management.base import BaseCommand

from core.models import (
    CriticalSuccessFactor,
    Indicator,
    Organization,
    OrganizationalUnit,
    Plan,
    PlanArtifact,
    StrategicAction,
    StrategicTarget,
)


class Command(BaseCommand):
    help = "Carrega OE 01, OE 02 e OE 03 do PEI 2025-2034 (piloto SRH)."

    def handle(self, *args, **options):
        sesed, _ = Organization.objects.get_or_create(
            acronym="SESED", defaults={"name": "Secretaria de Estado da Segurança Pública e Defesa Social"}
        )
        srh, _ = OrganizationalUnit.objects.get_or_create(
            organization=sesed,
            acronym="SRH",
            defaults={"name": "Setor de Recursos Humanos", "unit_type": OrganizationalUnit.UnitType.SECTOR},
        )
        gabinete, _ = OrganizationalUnit.objects.get_or_create(
            organization=sesed,
            acronym="GS",
            defaults={"name": "Gabinete do Secretário", "unit_type": OrganizationalUnit.UnitType.UNIT},
        )
        engenharia = self.unit(sesed, "ENG", "Setor de Engenharia")
        ciosp = self.unit(sesed, "CIOSP", "Centro Integrado de Operações de Segurança Pública")
        ctinf = self.unit(sesed, "CTINF", "Coordenadoria de Tecnologia e Informática")
        seaq = self.unit(sesed, "SEAQ", "Setor de Aquisições")
        funsep = self.unit(sesed, "FUNSEP", "Fundo Estadual de Segurança Pública")
        saf = self.unit(sesed, "SAF", "Subcoordenadoria de Administração e Finanças")
        spc = self.unit(sesed, "SPC", "Subcoordenadoria de Projetos e Convênios")
        copin = self.unit(sesed, "COPIN", "Coordenadoria de Planejamento Institucional")
        gsa = self.unit(sesed, "GSA", "Gabinete do Secretário Adjunto")
        cpcid = self.unit(sesed, "CPCID", "Coordenadoria de Programas para a Cidadania")
        codimm = self.unit(sesed, "CODIMM", "Coordenadoria de Defesa da Mulher e das Minorias")
        coine = self.unit(sesed, "COINE", "Coordenadoria de Informações Estatísticas e Análises Criminais")
        sesed_unit, _ = OrganizationalUnit.objects.get_or_create(
            organization=sesed,
            acronym="SESED",
            defaults={"name": "SESED - responsabilidade institucional", "unit_type": OrganizationalUnit.UnitType.ORGAN},
        )
        plan, _ = Plan.objects.update_or_create(
            acronym="PEI",
            defaults={
                "name": "Plano Estratégico Institucional da SESED 2025-2034",
                "plan_type": Plan.PlanType.PEI,
                "start_date": date(2025, 1, 1),
                "end_date": date(2034, 12, 31),
                "active": True,
            },
        )

        dimension = self.artifact(plan, None, PlanArtifact.ArtifactType.DIMENSION, "", "Gestão de Pessoas e Infraestrutura")
        axis_1 = self.artifact(plan, dimension, PlanArtifact.ArtifactType.AXIS, "Eixo 01", "Desenvolvimento de Recursos Humanos")
        axis_2 = self.artifact(plan, dimension, PlanArtifact.ArtifactType.AXIS, "Eixo 02", "Estruturação física")
        axis_3 = self.artifact(plan, dimension, PlanArtifact.ArtifactType.AXIS, "Eixo 03", "Desenvolvimento Tecnológico")
        axis_4 = self.artifact(plan, dimension, PlanArtifact.ArtifactType.AXIS, "Eixo 04", "Sustentabilidade Financeira")
        processes = self.artifact(plan, None, PlanArtifact.ArtifactType.DIMENSION, "", "Processos Internos")
        axis_5 = self.artifact(plan, processes, PlanArtifact.ArtifactType.AXIS, "Eixo 05", "Modelo de governança da SESED e da rede de segurança pública")
        axis_6 = self.artifact(plan, processes, PlanArtifact.ArtifactType.AXIS, "Eixo 06", "Modernização Organizacional")
        results = self.artifact(plan, None, PlanArtifact.ArtifactType.DIMENSION, "", "Resultados Institucionais")
        axis_7 = self.artifact(plan, results, PlanArtifact.ArtifactType.AXIS, "Eixo 07", "Parcerias Estratégicas")
        axis_8 = self.artifact(plan, results, PlanArtifact.ArtifactType.AXIS, "Eixo 08", "Reduzir os índices de criminalidade e ampliar a sensação de segurança")
        impact = self.artifact(plan, None, PlanArtifact.ArtifactType.DIMENSION, "", "Impacto para a Sociedade")
        axis_9 = self.artifact(plan, impact, PlanArtifact.ArtifactType.AXIS, "Eixo 09", "Fortalecimento de ações em Políticas Públicas")

        self.load_objective_01(plan, axis_1, srh)
        self.load_objective_02(plan, axis_1, srh, gabinete)
        self.load_objective_03(plan, axis_1, srh, gabinete)
        self.load_objective_04(plan, axis_2, gabinete, engenharia)
        self.load_objective_05(plan, axis_3, ctinf, ciosp)
        self.load_objective_06(plan, axis_4, saf, seaq, funsep, spc)
        self.load_objective_07(plan, axis_4, spc, gabinete)
        self.load_objective_08(plan, axis_5, copin, gabinete)
        self.load_objective_09(plan, axis_6, copin, gabinete, ciosp, ctinf)
        self.load_objective_10(plan, axis_6, copin, gsa)
        self.load_objective_11(plan, axis_7, gabinete, srh, ctinf, ciosp, copin)
        self.load_objective_12(plan, axis_8, sesed_unit)
        self.load_objective_13(plan, axis_9, cpcid, codimm, coine)
        # Metas e indicadores definitivos vêm do Quadro de Indicadores (Apêndice A) e sobrescrevem os textos acima.
        call_command("load_pei_indicators", stdout=self.stdout)
        self.stdout.write(self.style.SUCCESS("Carga do portfólio concluída: OE 01 a OE 13."))

    @staticmethod
    def unit(organization, acronym, name):
        unit, _ = OrganizationalUnit.objects.get_or_create(
            organization=organization,
            acronym=acronym,
            defaults={"name": name, "unit_type": OrganizationalUnit.UnitType.UNIT},
        )
        return unit

    @staticmethod
    def artifact(plan, parent, artifact_type, code, title):
        lookup = {"plan": plan, "artifact_type": artifact_type}
        if code:
            lookup["code"] = code
        else:
            lookup["title"] = title
        artifact, _ = PlanArtifact.objects.update_or_create(
            **lookup,
            defaults={"parent": parent, "code": code, "title": title},
        )
        return artifact

    @staticmethod
    def action(project, unit, code, title, funding_sources, participants=()):
        action, _ = StrategicAction.objects.update_or_create(
            artifact=project,
            code=code,
            defaults={
                "coordinating_unit": unit,
                "title": title,
                "due_date": None,
                "status": StrategicAction.Status.NOT_STARTED,
                "progress": 0,
                "funding_sources": funding_sources,
            },
        )
        action.participating_units.set(participants)
        return action

    @staticmethod
    def target(objective, code, description, value, period):
        target, _ = StrategicTarget.objects.update_or_create(
            artifact=objective,
            code=code,
            defaults={"description": description, "target_value": value, "reference_period": period},
        )
        return target

    @staticmethod
    def indicator(objective, target, unit, code, name, frequency, direction):
        code = "IE" + code[2:]  # o Quadro de Indicadores do PEI usa o prefixo IE para todos os indicadores
        indicator, _ = Indicator.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "description": name,
                "frequency": frequency,
                "direction": direction,
                "responsible_unit": unit,
            },
        )
        indicator.artifacts.set([objective])
        indicator.targets.set([target])
        return indicator

    @staticmethod
    def factors(project, descriptions):
        for description in descriptions:
            CriticalSuccessFactor.objects.get_or_create(artifact=project, description=description)

    def load_objective_01(self, plan, axis, srh):
        objective = self.artifact(plan, axis, PlanArtifact.ArtifactType.OBJECTIVE, "OE 01", "Implementar programa de capacitação continuada.")
        project = self.artifact(plan, objective, PlanArtifact.ArtifactType.PROJECT, "", "Implementação de Programa de Capacitação Continuada.")
        for code, title in [
            ("AE 01.1", "Realizar análise detalhada das competências necessárias para os profissionais da segurança pública."),
            ("AE 01.2", "Assegurar a capacitação continuada aos profissionais da SESED."),
            ("AE 01.3", "Desenvolver plano de monitoramento para acompanhar a implementação e o impacto das capacitações."),
        ]:
            self.action(project, srh, code, title, "Federais e Estadual")
        mt_1 = self.target(objective, "Mt 01.1", "Capacitar 100% dos servidores até 2034.", "100%", "Até 2034")
        mt_2 = self.target(objective, "Mt 01.2", "Atingir 70% de satisfação dos servidores a cada ciclo de capacitação.", "70%", "A cada ciclo de capacitação")
        self.indicator(objective, mt_1, srh, "IE 01.1", "Percentual de servidores capacitados anualmente.", Indicator.Frequency.ANNUAL, Indicator.Direction.HIGHER_IS_BETTER)
        self.indicator(objective, mt_2, srh, "IR 01.2", "Nível de satisfação dos servidores sobre as capacitações oferecidas.", Indicator.Frequency.ANNUAL, Indicator.Direction.HIGHER_IS_BETTER)
        self.factors(project, [
            "Engajamento contínuo dos servidores.",
            "Alocação de recursos financeiros e logísticos adequados para a capacitação.",
            "Disponibilidade de cursos e treinamentos de qualidade.",
        ])

    def load_objective_02(self, plan, axis, srh, gabinete):
        objective = self.artifact(plan, axis, PlanArtifact.ArtifactType.OBJECTIVE, "OE 02", "Ampliar o quadro de servidores da SESED.")
        project = self.artifact(plan, objective, PlanArtifact.ArtifactType.PROJECT, "", "Ampliação do quadro de efetivo de servidores da SESED.")
        for code, title in [
            ("AE 02.1", "Realização de concurso público."),
            ("AE 02.2", "Formalização de acordo de cessão de profissionais do SISPRN para suprir demanda de pessoal da SESED."),
        ]:
            self.action(project, gabinete, code, title, "Tesouro Estadual", [srh])
        mt_1 = self.target(objective, "Mt 02.1", "Crescer o quadro de servidores em 10% até 2034.", "10%", "Até 2034")
        mt_2 = self.target(objective, "Mt 02.2", "Reduzir em 10% o tempo médio do processo nos setores.", "10%", "A definir")
        self.indicator(objective, mt_1, srh, "IE 02.1", "Taxa de crescimento do quadro de servidores.", Indicator.Frequency.BIENNIAL, Indicator.Direction.HIGHER_IS_BETTER)
        self.indicator(objective, mt_2, srh, "IR 02.2", "Tempo médio de execução dos processos.", Indicator.Frequency.ANNUAL, Indicator.Direction.LOWER_IS_BETTER)
        self.factors(project, [
            "Disponibilidade de orçamento para novas contratações.",
            "Aprovação e execução de concursos públicos.",
            "Realização de estudo de efetivo para fundamentar a demanda.",
            "Planejamento estratégico para integração dos novos servidores.",
        ])

    def load_objective_03(self, plan, axis, srh, gabinete):
        objective = self.artifact(plan, axis, PlanArtifact.ArtifactType.OBJECTIVE, "OE 03", "Promover a Qualidade de Vida e Saúde no Trabalho (QVST).")
        project = self.artifact(plan, objective, PlanArtifact.ArtifactType.PROJECT, "", "Elaboração e implementação de Programa de Qualidade de Vida e Saúde no Trabalho.")
        for code, title in [
            ("AE 03.1", "Criação de um programa de QVST."),
            ("AE 03.2", "Realização de iniciativas voltadas para a QVST."),
        ]:
            self.action(project, gabinete, code, title, "Tesouro Estadual", [srh])
        targets = [
            ("Mt 03.1", "Implantar Programa de Qualidade de Vida e Saúde até 2034.", "Até 2034", "IE 03.1", "Índice de implementação do Programa de QVST.", Indicator.Direction.HIGHER_IS_BETTER),
            ("Mt 03.2", "Realizar 3 iniciativas de QVST anualmente.", "3 iniciativas", "IR 03.2", "Total de atividades de QVST realizadas.", Indicator.Direction.HIGHER_IS_BETTER),
            ("Mt 03.3", "Alcançar nível de satisfação acima de 70% dentre os participantes.", "70%", "IR 03.3", "Percentual de satisfação dos servidores participantes das ações de QVST.", Indicator.Direction.HIGHER_IS_BETTER),
            ("Mt 03.4", "Alcançar participação de 70% dos servidores nas atividades realizadas anualmente.", "70%", "IE 03.4", "Percentual de participação dos servidores.", Indicator.Direction.HIGHER_IS_BETTER),
        ]
        for target_code, description, value, indicator_code, indicator_name, direction in targets:
            target = self.target(objective, target_code, description, value, "Anual, a contar de 2026")
            self.indicator(objective, target, srh, indicator_code, indicator_name, Indicator.Frequency.ANNUAL, direction)
        self.factors(project, [
            "Participação ativa dos servidores no programa.",
            "Suporte adequado de infraestrutura e recursos.",
            "Integração das ações de qualidade de vida com a gestão estratégica.",
        ])

    def load_objective_04(self, plan, axis, gabinete, engenharia):
        objective = self.artifact(plan, axis, PlanArtifact.ArtifactType.OBJECTIVE, "OE 04", "Prover condições físicas adequadas para as atividades laborais dos servidores e atendimento público.")
        project = self.artifact(plan, objective, PlanArtifact.ArtifactType.PROJECT, "", "Provimento de condições físicas adequadas para atividades laborais dos servidores da Secretaria de Segurança Pública e Defesa Social.")
        for code, title in [
            ("AE 04.1", "Definição da área onde será construída a sede da SESED."),
            ("AE 04.2", "Elaborar estudos e projetos para viabilizar uma sede própria para a SESED."),
        ]:
            self.action(project, gabinete, code, title, "Recursos Federais e Tesouro Estadual", [engenharia])
        target = self.target(objective, "Mt 04.1", "Construir uma sede própria para a SESED até 2034.", "Até 2034", "Até 2034")
        self.indicator(objective, target, engenharia, "IE 04.1", "Percentual de construção da Sede.", Indicator.Frequency.ANNUAL, Indicator.Direction.HIGHER_IS_BETTER)
        self.factors(project, [
            "Planejamento adequado de arquitetura e logística.",
            "Garantia de recursos financeiros para a obra.",
            "Monitoramento contínuo do andamento do projeto.",
        ])

    def load_objective_05(self, plan, axis, ctinf, ciosp):
        objective = self.artifact(plan, axis, PlanArtifact.ArtifactType.OBJECTIVE, "OE 05", "Expandir e Modernizar a infraestrutura de Tecnologia da Informação e Comunicação da SESED.")
        project = self.artifact(plan, objective, PlanArtifact.ArtifactType.PROJECT, "", "Modernização e expansão da infraestrutura de Tecnologia da Informação e Comunicação da SESED.")
        actions = [
            ("AE 05.1", "Modernização da infraestrutura de TIC, com foco na aquisição de novos equipamentos e softwares, ampliação da gestão dos ativos de redes e atualizações dos gerenciadores de banco de dados existentes na SESED."),
            ("AE 05.2", "Expansão territorial e modernização da infraestrutura de radiocomunicação digital nas operações da SESED."),
            ("AE 05.3", "Implantação do DataCenter de Backup da SESED até 2034."),
            ("AE 05.4", "Automação de processos, análise preditiva e monitoramento inteligente, com inteligência artificial e Machine Learning, nos sistemas desenvolvidos pela SESED."),
            ("AE 05.5", "Fortalecimento da cibersegurança, protegendo dados sensíveis e sistemas críticos de ataques cibernéticos."),
            ("AE 05.6", "Ampliação do Sistema para os municípios da região metropolitana de Natal."),
            ("AE 05.7", "Fortalecer a colaboração e a integração entre os sistemas do SISP, promovendo interoperabilidade, troca eficiente de informações e coordenação de operações."),
        ]
        for code, title in actions:
            self.action(project, ctinf, code, title, "Recursos Federais e Tesouro Estadual", [ciosp])
        targets = [
            ("Mt 05.1", "Expandir o sistema de radiocomunicação digital troncalizado para 50% do território do RN.", "50%", "IE 05.1", "Taxa de expansão da cobertura de radiocomunicação digital no RN.", Indicator.Frequency.BIENNIAL),
            ("Mt 05.2", "Implantar o DataCenter de Backup da SESED.", "", "IE 05.2", "Índice de implementação do DataCenter.", Indicator.Frequency.BIENNIAL),
            ("Mt 05.3", "Realizar 10 ações de modernização em Tecnologia da Informação e Comunicação.", "10 ações", "IE 05.3", "Percentual de ações realizadas.", Indicator.Frequency.ANNUAL),
            ("Mt 05.4", "Integrar 100% dos sistemas da Secretaria com as outras forças de segurança até 2034.", "100%", "IE 05.4", "Percentual de integração dos sistemas entre as forças de segurança.", Indicator.Frequency.ANNUAL),
        ]
        for code, description, value, indicator_code, name, frequency in targets:
            target = self.target(objective, code, description, value, "A partir de 2026" if frequency == Indicator.Frequency.BIENNIAL else "Anual")
            self.indicator(objective, target, ctinf, indicator_code, name, frequency, Indicator.Direction.HIGHER_IS_BETTER)
        self.factors(project, [
            "Seleção e compra de equipamentos adequados.",
            "Capacitação da equipe para a operação do DataCenter.",
            "Suporte técnico contínuo para manutenção do sistema.",
            "Integração eficaz dos sistemas tecnológicos.",
            "Alinhamento entre os recursos financeiros, humanos e tecnológicos.",
            "Capacitação contínua da equipe e alocação eficiente de recursos.",
            "Integração e colaboração interinstitucional, com protocolos de comunicação.",
            "Implementação de medidas robustas de segurança da informação.",
            "Implementação de inteligência artificial e análise dos sistemas da SESED na prevenção e resposta a crimes.",
        ])

    def load_objective_06(self, plan, axis, saf, seaq, funsep, spc):
        objective = self.artifact(plan, axis, PlanArtifact.ArtifactType.OBJECTIVE, "OE 06", "Fortalecer a Execução Financeira e Orçamentária.")
        project = self.artifact(plan, objective, PlanArtifact.ArtifactType.PROJECT, "", "Otimização da execução financeira e orçamentária da SESED.")
        for code, title in [
            ("AE 06.1", "Implementar no âmbito do SISPRN a portaria de regulação do uso dos recursos do FNSP."),
            ("AE 06.2", "Elevar a quantidade de recursos pagos provenientes do FNSP."),
        ]:
            self.action(project, saf, code, title, "Recursos Federais e Tesouro Estadual", [seaq, funsep, spc])
        targets = [
            ("Mt 06.1", "Aumentar a eficácia da execução financeira em 5% anualmente.", "5%", "IE 06.1", "Percentual de execução de recursos orçamentários SESED."),
            ("Mt 06.2", "Aumentar a execução orçamentária dos recursos Fundo a Fundo em 10% até 2034.", "10%", "IR 06.2", "Percentual de execução de recursos orçamentários do FaF."),
        ]
        for code, description, value, indicator_code, name in targets:
            target = self.target(objective, code, description, value, "Anual")
            self.indicator(objective, target, saf, indicator_code, name, Indicator.Frequency.ANNUAL, Indicator.Direction.HIGHER_IS_BETTER)
        self.factors(project, [
            "Adoção de ferramentas de gestão financeira eficazes.",
            "Alocação de recursos humanos capacitados para o controle financeiro.",
            "Monitoramento contínuo dos processos orçamentários.",
        ])

    def load_objective_07(self, plan, axis, spc, gabinete):
        objective = self.artifact(plan, axis, PlanArtifact.ArtifactType.OBJECTIVE, "OE 07", "Ampliar a captação de recursos externos.")
        project = self.artifact(plan, objective, PlanArtifact.ArtifactType.PROJECT, "", "Ampliação da captação de emendas individuais, de bancada e programas ministeriais.")
        for code, title in [
            ("AE 07.1", "Ampliar a captação de recursos financeiros por meio de emendas parlamentares e programas ministeriais."),
            ("AE 07.2", "Diversificação de fontes de financiamento (PPP, FINEP, dentre outros)."),
        ]:
            self.action(project, spc, code, title, "Tesouro Estadual", [gabinete])
        targets = [
            ("Mt 07.1", "Aumentar em 10% a captação de recursos externos.", "10%", "IE 07.1", "Índice de captação de recursos externos."),
            ("Mt 07.2", "Realizar 40 ações para captação de recursos até 2034.", "40 ações", "IE 07.2", "Percentual de ações para captação de recursos."),
            ("Mt 07.3", "Implementar a assessoria parlamentar da SESED para captação de recursos.", "", "IE 07.3", "Percentual de avanço da implementação da assessoria parlamentar da SESED."),
        ]
        for code, description, value, indicator_code, name in targets:
            target = self.target(objective, code, description, value, "Anual")
            self.indicator(objective, target, spc, indicator_code, name, Indicator.Frequency.ANNUAL, Indicator.Direction.HIGHER_IS_BETTER)
        self.factors(project, [
            "Identificação de novas fontes de recursos.",
            "Efetiva comunicação com parlamentares e ministérios.",
            "Equipe especializada na captação de recursos e elaboração de projetos.",
        ])

    def load_objective_08(self, plan, axis, copin, gabinete):
        objective = self.artifact(plan, axis, PlanArtifact.ArtifactType.OBJECTIVE, "OE 08", "Aprimorar o papel de Governança por meio da implementação de Gestão por Resultados no SISPRN.")
        project = self.artifact(plan, objective, PlanArtifact.ArtifactType.PROJECT, "", "Implementação de comissões e/ou setores internos de governança em todos os órgãos do SISPRN.")
        for code, title in [
            ("AE 08.1", "Mapeamento e diagnóstico inicial dos órgãos do SISPRN quanto à governança (2025)."),
            ("AE 08.2", "Criação das Diretrizes de Governança."),
            ("AE 08.3", "Criação de sistema de monitoramento e avaliação dos resultados atingidos de cada órgão."),
            ("AE 08.4", "Implementação de comissões/setores de governança nos órgãos do SISPRN."),
        ]:
            self.action(project, copin, code, title, "Recursos Federais e Tesouro Estadual", [gabinete])
        targets = [
            ("Mt 08.1", "Estruturar 100% dos órgãos do SISPRN com setores de governança até 2034.", "100%", "IE 08.1", "Percentual de órgãos do SISPRN com setores estruturados de governança."),
            ("Mt 08.2", "Adesão de 100% dos órgãos do SISPRN ao modelo de Gestão por Resultados.", "100%", "IR 08.2", "Índice de adesão às boas práticas de governança estabelecidas."),
        ]
        for code, description, value, indicator_code, name in targets:
            target = self.target(objective, code, description, value, "Anual, a partir de 2026")
            self.indicator(objective, target, copin, indicator_code, name, Indicator.Frequency.ANNUAL, Indicator.Direction.HIGHER_IS_BETTER)
        self.factors(project, [
            "Adesão dos órgãos ao processo de governança.",
            "Capacitação contínua das comissões de governança.",
            "Monitoramento da implementação e eficácia das estratégias de gestão.",
        ])

    def load_objective_09(self, plan, axis, copin, gabinete, ciosp, ctinf):
        objective = self.artifact(plan, axis, PlanArtifact.ArtifactType.OBJECTIVE, "OE 09", "Fomentar a cultura de inovação na Segurança Pública.")
        project = self.artifact(plan, objective, PlanArtifact.ArtifactType.PROJECT, "", "Criação, implementação e manutenção de laboratórios e de soluções de TIC voltados para a inovação na Segurança Pública.")
        for code, title in [
            ("AE 09.1", "Criação e implementação do Laboratório de Visão Computacional voltado para a inovação na Segurança Pública."),
            ("AE 09.2", "Desenvolvimento de plataformas para integração de dados de diversas agências."),
            ("AE 09.3", "Implementação de soluções inovadoras."),
        ]:
            self.action(project, copin, code, title, "Recursos Federais e Tesouro Estadual", [gabinete, ciosp, ctinf])
        targets = [
            ("Mt 09.1", "Implementar laboratórios de inovação até 2034.", "Até 2034", "IE 09.1", "Percentual de implantação do laboratório de inovação.", "Anual, a partir de 2026"),
            ("Mt 09.2", "Implementar 15 soluções inovadoras até 2034.", "15 soluções", "IE 09.2", "Índice de soluções inovadoras implementadas.", "Anual"),
        ]
        for code, description, value, indicator_code, name, period in targets:
            target = self.target(objective, code, description, value, period)
            self.indicator(objective, target, copin, indicator_code, name, Indicator.Frequency.ANNUAL, Indicator.Direction.HIGHER_IS_BETTER)
        self.factors(project, [
            "Obtenção de recursos financeiros e tecnológicos para implementação dos laboratórios.",
            "Participação ativa de especialistas e técnicos.",
            "Adoção de práticas de inovação tecnológica contínuas.",
        ])

    def load_objective_10(self, plan, axis, copin, gsa):
        objective = self.artifact(plan, axis, PlanArtifact.ArtifactType.OBJECTIVE, "OE 10", "Implementar a gestão por processos.")
        project = self.artifact(plan, objective, PlanArtifact.ArtifactType.PROJECT, "", "Elaboração e implementação de projeto de mapeamento, melhoria e padronização dos processos da SESED.")
        for code, title in [
            ("AE 10.1", "Mapeamento e análise dos processos (2025-2026)."),
            ("AE 10.2", "Padronização e redesenho dos processos (2025 em diante)."),
            ("AE 10.3", "Implementação de cultura de monitoramento e avaliação contínuos (2026 e além)."),
        ]:
            self.action(project, copin, code, title, "Recursos Federais e Tesouro Estadual", [gsa])
        targets = [
            ("Mt 10.1", "Padronizar 10 processos anualmente até 2034.", "10 processos", "IE 10.1", "Percentual de processos padronizados na SESED.", Indicator.Direction.HIGHER_IS_BETTER, "Anual"),
            ("Mt 10.2", "Elaborar 10 cartilhas, guias ou manuais de procedimento operacional-padrão até 2034.", "10 documentos", "IE 10.2", "Percentual de criação de cartilhas, guias ou manuais.", Indicator.Direction.HIGHER_IS_BETTER, "Anual"),
            ("Mt 10.3", "Reduzir em 10% o tempo médio de execução dos processos.", "10%", "IR 10.3", "Índice de redução do tempo médio de execução dos processos.", Indicator.Direction.LOWER_IS_BETTER, "Anual, a partir de 2026"),
        ]
        for code, description, value, indicator_code, name, direction, period in targets:
            target = self.target(objective, code, description, value, period)
            self.indicator(objective, target, copin, indicator_code, name, Indicator.Frequency.ANNUAL, direction)
        self.factors(project, [
            "Engajamento das áreas envolvidas no processo de padronização.",
            "Implementação de sistemas eficazes para automatizar processos.",
            "Monitoramento contínuo da melhoria dos fluxos operacionais.",
        ])

    def load_objective_11(self, plan, axis, gabinete, srh, ctinf, ciosp, copin):
        objective = self.artifact(plan, axis, PlanArtifact.ArtifactType.OBJECTIVE, "OE 11", "Ampliar parcerias com instituições de ensino e de pesquisa científica.")
        project = self.artifact(plan, objective, PlanArtifact.ArtifactType.PROJECT, "", "Formalização de cooperação com instituições de pesquisa e de ensino.")
        self.action(project, gabinete, "AE 11.1", "Efetivação de cooperação com instituições de pesquisa e de ensino para desenvolver ações na área da segurança pública.", "Recursos Federais e Estadual", [srh, ctinf, ciosp, copin])
        targets = [
            ("Mt 11.1", "Efetivar 5 novas parcerias até 2034.", "5 parcerias", "IE 11.1", "Índice de parcerias efetivas."),
            ("Mt 11.2", "Efetivar 5 projetos colaborativos até 2034.", "5 projetos", "IR 11.2", "Índice de projetos colaborativos efetivados."),
        ]
        for code, description, value, indicator_code, name in targets:
            target = self.target(objective, code, description, value, "Bienal")
            self.indicator(objective, target, gabinete, indicator_code, name, Indicator.Frequency.BIENNIAL, Indicator.Direction.HIGHER_IS_BETTER)
        self.factors(project, [
            "Engajamento e colaboração eficaz com instituições de pesquisa.",
            "Identificação de áreas prioritárias para pesquisa e inovação.",
            "Alocação de recursos para projetos de pesquisa conjunta.",
        ])

    def load_objective_12(self, plan, axis, sesed_unit):
        objective = self.artifact(plan, axis, PlanArtifact.ArtifactType.OBJECTIVE, "OE 12", "Articular e coordenar a realização de operações especiais integradas com a participação dos órgãos que compõem o SISPRN, MP e TJ para reduzir índices de criminalidade.")
        project = self.artifact(plan, objective, PlanArtifact.ArtifactType.PROJECT, "", "Fomento a operações especiais integradas de repressão qualificada.")
        self.action(project, sesed_unit, "AE 12.1", "Coordenação de operações integradas entre os órgãos do SISPRN e de apoio ao Ministério Público e Tribunal de Justiça.", "Recursos Federais e Estadual")
        targets = [
            ("Mt 12.1", "Articular 10 operações especiais integradas até 2034.", "10 operações", "IE 12.1", "Percentual de operações especiais articuladas pela SESED.", Indicator.Direction.HIGHER_IS_BETTER),
            ("Mt 12.2", "Reduzir índices de homicídios para 20 por 100 mil habitantes até 2034.", "20 por 100 mil", "IR 12.2", "Taxa de índices de homicídios.", Indicator.Direction.LOWER_IS_BETTER),
            ("Mt 12.3", "Reduzir a taxa de mortes violentas de mulheres para abaixo de 3 até 2034.", "Abaixo de 3", "IR 12.3", "Taxa de mortes violentas de mulheres.", Indicator.Direction.LOWER_IS_BETTER),
            ("Mt 12.4", "Aumentar em 10% a quantidade de drogas apreendidas, em kg.", "10%", "IR 12.4", "Quantidade de drogas apreendidas.", Indicator.Direction.HIGHER_IS_BETTER),
            ("Mt 12.5", "Reduzir o número de ocorrências de poluição sonora e perturbação do sossego alheio em 50% até 2034.", "50%", "IR 12.5", "Índice de ocorrências registradas pelo 190 (CIOSP).", Indicator.Direction.LOWER_IS_BETTER),
        ]
        for code, description, value, indicator_code, name, direction in targets:
            target = self.target(objective, code, description, value, "Anual")
            self.indicator(objective, target, sesed_unit, indicator_code, name, Indicator.Frequency.ANNUAL, direction)
        self.factors(project, [
            "Coordenação eficaz entre os diversos órgãos envolvidos.",
            "Monitoramento contínuo dos resultados das operações.",
            "Avaliação de impacto das operações na redução da criminalidade.",
        ])

    def load_objective_13(self, plan, axis, cpcid, codimm, coine):
        objective = self.artifact(plan, axis, PlanArtifact.ArtifactType.OBJECTIVE, "OE 13", "Fortalecer a comunicação, participação social e cidadania nas ações de segurança pública.")
        project = self.artifact(plan, objective, PlanArtifact.ArtifactType.PROJECT, "", "Fortalecimento da comunicação, participação social e cidadania nas ações de segurança.")
        for code, title in [
            ("AE 13.1", "Implementação do Programa Policial Educador."),
            ("AE 13.2", "Estímulo à formação e implementação de Conselhos Comunitários de Defesa Social."),
            ("AE 13.3", "Criação do projeto Cidadania Ativa, de fomento à participação social em Segurança Pública."),
            ("AE 13.4", "Promoção de ações comunitárias, seminários, webinars, conferências e oficinas educativas."),
            ("AE 13.5", "Publicação da revista Cidadania & Segurança Pública."),
            ("AE 13.6", "Criação do Programa de Enfrentamento aos Racismos, Torturas e outras Violências - P.E.R.T.O."),
            ("AE 13.7", "Publicação de boletins trimestrais de conjuntura criminal."),
        ]:
            self.action(project, cpcid, code, title, "Recursos Federais e Estadual", [codimm, coine])
        targets = [
            ("Mt 13.1", "Criar e implementar o Programa Policial Educador.", "", "IE 13.1", "Percentual de criação e implementação do programa Policial Educador.", Indicator.Direction.HIGHER_IS_BETTER),
            ("Mt 13.2", "Realizar 10 ações de fomento à cidadania e participação social até 2034.", "10 ações", "IE 13.2", "Índice de ações de fomento à cidadania e participação social.", Indicator.Direction.HIGHER_IS_BETTER),
            ("Mt 13.3", "Atingir o engajamento de 70% dos participantes nas ações de fomento à cidadania.", "70%", "IR 13.3", "Índice de engajamento dos participantes nas ações de fomento à cidadania.", Indicator.Direction.HIGHER_IS_BETTER),
            ("Mt 13.4", "Expandir a 100% dos municípios do RN a criação dos CCDS.", "100%", "IE 13.4", "Percentual de formação e implementação dos CCDS.", Indicator.Direction.HIGHER_IS_BETTER),
            ("Mt 13.5", "Publicar 10 edições da revista Cidadania & Segurança Pública até 2034.", "10 edições", "IE 13.5", "Percentual de publicação da revista Cidadania & Segurança Pública.", Indicator.Direction.HIGHER_IS_BETTER),
        ]
        for code, description, value, indicator_code, name, direction in targets:
            target = self.target(objective, code, description, value, "Anual")
            self.indicator(objective, target, cpcid, indicator_code, name, Indicator.Frequency.ANNUAL, direction)
        self.factors(project, [
            "Adesão das comunidades ao programa.",
            "Capacitação contínua dos policiais envolvidos no projeto.",
            "Monitoramento e avaliação do impacto das ações no fortalecimento da cidadania.",
            "Engajamento das comunidades na formação dos conselhos.",
            "Suporte institucional para a criação e manutenção dos conselhos.",
            "Monitoramento contínuo das ações realizadas pelos conselhos.",
        ])
