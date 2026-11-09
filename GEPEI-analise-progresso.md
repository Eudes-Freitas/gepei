# GEPEI — progresso da análise

## Decisões aprovadas

1. O modelo será reduzido por consolidação de tabelas, sem perder dados ou lógica.
2. Usuário pertence a apenas um grupo.
3. Permissões pertencem ao grupo; não haverá permissões específicas por usuário.
4. Remover as tabelas intermediárias de autenticação:
   - `auth_user_groups`
   - `auth_user_user_permissions`
   - `auth_group_permissions`
5. Remover a hierarquia entre unidades organizacionais; `organizational_unit` não terá `parent_id`.
6. Consolidar artefatos, ações estratégicas, metas e fatores críticos em `plan_item`, usando `kind`.
7. Consolidar bloqueios e evidências em `activity_record`, usando `kind`.
8. Consolidar relações de indicadores em `indicator_link`, usando `link_kind`.
9. Consolidar todos os registros de risco em uma única tabela `risk`, usando `record_type` e mantendo histórico.
10. O PDF gráfico será atualizado somente após a análise de todos os conjuntos.

## Conjuntos já analisados

- Planejamento e atividades.
- Indicadores.
- Organização e usuários.
- Riscos: `risk` como registro principal e `risk_event` como histórico consolidado de avaliações, tratamentos, materializações, aceites e remediações.
- Relatórios e validações: `report_cycle` e `report`; removido `report_cycle_unit` e removido o prazo obrigatório de envio (`due_date`).
- Auditoria e notificações: mantidos `audit_log` e `notification` separadamente, por terem funções e ciclos de vida diferentes.
- Integração entre planos: mantida uma única tabela opcional `plan_link` para relações entre elementos de planos.

## Próximo conjunto

- Revisão final do modelo consolidado e atualização do DBML/PDF.

## Arquivos principais

- `GEPEI-minimo.dbml` — modelo lógico em revisão.
- `GEPEI-minimo-notas.md` — notas da proposta.
- `GEPEI-minimo-grafico.pdf` — PDF anterior; atualizar ao final.
