# Backlog do MVP - Plataforma de Gestão Integrada da Estratégia

**Versão:** 0.1  
**Data:** 18 de julho de 2026  
**Referência:** [Documento de Visão e Escopo do MVP](DOCUMENTO_DE_VISAO_E_ESCOPO_MVP.md)

## Prioridades

- **P0 - indispensável:** necessário para o piloto funcionar.
- **P1 - logo após o piloto:** amplia a abrangência e a integração.
- **P2 - evolução futura:** agrega conveniência, sem bloquear o uso.

## Épico 1 - Acesso, organização e permissões (P0)

| ID | História de usuário | Critério de aceite resumido |
|---|---|---|
| MVP-01 | Como administrador, quero cadastrar órgãos, unidades e setores em uma hierarquia organizacional. | É possível estruturar SESED → órgão/unidade → setor e associar responsáveis. |
| MVP-02 | Como administrador, quero criar contas e atribuir perfis. | Perfis: administrador, COPIN, chefia, responsável por ação e visualizador. |
| MVP-03 | Como usuário, quero acessar o sistema com conta e senha. | O acesso é autenticado e respeita as permissões do perfil. |
| MVP-04 | Como administrador, quero registrar os setores do piloto. | COPIN, FUNSEP, CTINF, CPCID, CODIMM e CIOSP ficam disponíveis para associação aos registros. |

## Épico 2 - PEI e estrutura estratégica (P0)

| ID | História de usuário | Critério de aceite resumido |
|---|---|---|
| MVP-05 | Como COPIN, quero cadastrar ou importar o PEI. | O PEI pode registrar dimensões BSC, eixos, objetivos, projetos, ações, metas e indicadores. |
| MVP-06 | Como COPIN, quero importar dados dos artefatos originais e revisá-los antes da publicação. | Dados importados ficam em revisão; somente após validação da COPIN são publicados. |
| MVP-07 | Como COPIN, quero manter versões formais de planos, metas e indicadores. | Revisões preservam versões anteriores e sua vigência. |
| MVP-08 | Como usuário autorizado, quero navegar do plano até suas ações e indicadores. | A navegação apresenta a cadeia estratégica e seus responsáveis. |

## Épico 3 - Ações estratégicas e plano de ação operacional (P0)

| ID | História de usuário | Critério de aceite resumido |
|---|---|---|
| MVP-09 | Como COPIN, quero cadastrar ações estratégicas vinculadas ao PEI. | Ações têm unidade coordenadora, setores participantes quando aplicável, prazo, status, percentual, riscos, recursos e observações. |
| MVP-10 | Como gestor da ação estratégica, quero criar atividades e atribuí-las a pessoas executoras. | Atividades possuem título, descrição, pessoa executora, prazo, peso, status, recursos, dependências, entrega/produto e evidências. |
| MVP-11 | Como responsável, quero distribuir pesos entre atividades. | O sistema exige total de 100% para as atividades de cada ação. |
| MVP-12 | Como COPIN, quero calcular a execução da ação a partir das atividades ponderadas. | O percentual calculado é exibido; a configuração pode permitir ajuste manual justificado. |
| MVP-13 | Como usuário autorizado, quero reabrir uma ação ou atividade concluída para corrigir registro indevido. | Reabertura exige justificativa e preserva o histórico. |
| MVP-14 | Como gestor, quero acompanhar projetos transversais. | Projetos estratégicos podem ter unidade gestora, unidades participantes, gestor de projeto e atividades atribuídas individualmente. |

## Épico 4 - Atualizações, entregas, recursos e evidências (P0)

| ID | História de usuário | Critério de aceite resumido |
|---|---|---|
| MVP-15 | Como pessoa executora, quero registrar execução, comentários, dificuldades, barreiras e riscos de minhas atividades quando ocorrerem. | Os registros refletem o estado atual e são reunidos automaticamente no ciclo de relatório. |
| MVP-16 | Como responsável, quero registrar entregas e produtos esperados. | O registro diferencia entrega e produto e permite associar evidência. |
| MVP-17 | Como responsável, quero anexar PDF, imagem ou link/SEI como evidência. | Cada evidência registra descrição, data e autor; limite de tamanho é configurável. |
| MVP-18 | Como responsável, quero registrar recursos financeiros, logísticos e de pessoal usados em uma atividade. | Recursos financeiros incluem valor e fonte: FAF, convênio ou tesouro estadual. |
| MVP-19 | Como COPIN, quero consultar a trilha de auditoria de alterações relevantes. | Alterações registram autor, data/hora, valor anterior, novo valor e justificativa. |

## Épico 5 - Riscos, dependências e alertas (P0)

| ID | História de usuário | Critério de aceite resumido |
|---|---|---|
| MVP-20 | Como responsável, quero manter o mapa de riscos da ação e de suas atividades. | Cada risco registra identificação, causas, item afetado, responsável, probabilidade, impacto, nível, avaliação, tratamento, medidas preventivas, contingência e situação. |
| MVP-21 | Como gestor, quero visualizar riscos materializados sem alteração automática indevida do status. | A materialização é registrada e seu efeito depende do tratamento definido. |
| MVP-22 | Como responsável, quero indicar dependências entre atividades e ações. | Dependências são visíveis e podem sinalizar impacto de atraso. |
| MVP-23 | Como usuário, quero receber alertas de prazo próximo, prazo vencido e ausência de atualização. | Alertas aparecem no sistema e por e-mail para responsável, chefia e COPIN. |
| MVP-24 | Como sistema, quero mudar automaticamente uma ação ou atividade para atrasada após o prazo. | A mudança ocorre após o vencimento; bloqueio exige motivo, responsável pela solução e previsão de desbloqueio. |

## Épico 6 - Indicadores, metas e semáforos (P0)

| ID | História de usuário | Critério de aceite resumido |
|---|---|---|
| MVP-25 | Como COPIN, quero cadastrar indicadores conforme o PEI. | Indicador contém fórmula, unidade, fonte, periodicidade, linha de base, meta e responsável. |
| MVP-26 | Como responsável, quero informar valores de aferição por período. | O histórico de valores é preservado e pode ser consultado. |
| MVP-27 | Como COPIN, quero relacionar indicadores a metas e objetivos. | Uma meta pode ter vários indicadores e um indicador pode medir vários objetivos. |
| MVP-28 | Como gestor, quero visualizar semáforos de indicadores, metas, ações e orçamento. | Verde, amarelo, vermelho e cinza refletem regras configuráveis. |

## Épico 7 - Painéis de acompanhamento (P0)

| ID | História de usuário | Critério de aceite resumido |
|---|---|---|
| MVP-29 | Como COPIN, quero um painel consolidado de execução. | Exibe metas, objetivos, ações, responsáveis, riscos, recursos e atrasos por período e unidade. |
| MVP-30 | Como Secretário ou visualizador autorizado, quero um painel executivo simplificado. | Destaca PEI e PESP, percentual de execução, itens críticos e responsáveis. |
| MVP-31 | Como usuário, quero filtrar painéis. | Filtros: plano, objetivo, setor/órgão, período, status e fonte de recurso. |
| MVP-32 | Como usuário, quero acessar o sistema por computador e celular. | Telas essenciais são responsivas. |

## Épico 8 - Ciclo de relatório e consolidação (P0)

| ID | História de usuário | Critério de aceite resumido |
|---|---|---|
| MVP-33 | Como COPIN, quero configurar ciclo trimestral, quadrimestral, semestral ou anual. | O ciclo possui período, prazo e planos/unidades participantes. |
| MVP-34 | Como responsável de setor, quero revisar e enviar o relatório do período. | O relatório reúne automaticamente dados, inclusive barreiras e riscos já registrados, mas permite comentário final, justificativas e complementos. |
| MVP-35 | Como validador designado, quero validar ou devolver o relatório setorial. | A devolução registra comentário e novo prazo; o sistema exige validador alternativo quando houver conflito de autoaprovação. |
| MVP-36 | Como COPIN, quero consolidar relatórios setoriais. | O sistema gera um relatório institucional com resultados, barreiras, riscos, providências e pendências. |
| MVP-37 | Como COPIN, quero fechar o período preservando seus dados. | O fechamento bloqueia alterações comuns e mantém a fotografia do período. |
| MVP-38 | Como COPIN, quero exportar relatórios. | Relatórios podem ser visualizados e exportados em PDF, Excel e Word. |

## Épico 9 - Integração entre instrumentos de planejamento (P1)

| ID | História de usuário | Critério de aceite resumido |
|---|---|---|
| MVP-39 | Como COPIN, quero relacionar artefatos entre PEI, PESP, PPA e demais planos. | Vínculos diretos e indiretos podem ser cadastrados e consultados. |
| MVP-40 | Como COPIN, quero definir tipo e peso de cada vínculo. | Tipos: contribui para, financia, mede, executa, depende de, está alinhado a e é evidência de. |
| MVP-41 | Como usuário, quero visualizar na ação os planos, metas e indicadores vinculados. | A tela mostra vínculo principal, demais vínculos, peso e impacto. |
| MVP-42 | Como COPIN, quero cadastrar estrutura completa de PESP e PPA. | Cada plano pode ter hierarquia própria e artefatos específicos. |

## Épico 10 - Financeiro ampliado (P1)

| ID | História de usuário | Critério de aceite resumido |
|---|---|---|
| MVP-43 | Como responsável, quero registrar orçamento previsto, empenhado, liquidado e pago. | Valores manuais são associados a ação, atividade, fonte e programa/ação orçamentária. |
| MVP-44 | Como gestor, quero acompanhar execução financeira em painéis e relatórios. | Painel permite filtro por fonte de recurso e indica semáforo de orçamento. |

## Épico 11 - Base de conhecimento (P2)

| ID | História de usuário | Critério de aceite resumido |
|---|---|---|
| MVP-45 | Como COPIN, quero publicar orientações, manuais e modelos. | Conteúdo pode ser organizado e acessado pelos setores. |

## Ordem sugerida de entregas

1. Fundamentos: MVP-01 a MVP-04.
2. PEI e navegação estratégica: MVP-05 a MVP-08.
3. Plano de ação e atualizações: MVP-09 a MVP-19.
4. Riscos, dependências e alertas: MVP-20 a MVP-24.
5. Indicadores, metas e semáforos: MVP-25 a MVP-28.
6. Painéis: MVP-29 a MVP-32.
7. Relatório e consolidação: MVP-33 a MVP-38.
8. Evoluções P1 e P2: MVP-39 a MVP-45.

## Itens a detalhar na etapa de prototipação

- regras numéricas de semáforo por tipo de indicador e orçamento;
- limites e políticas de anexos;
- desenho da tela de vínculo entre planos;
- campos finais de cada formulário;
- modelo visual do relatório trimestral;
- regras de notificação por e-mail.
