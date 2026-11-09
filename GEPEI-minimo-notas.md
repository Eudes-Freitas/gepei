# GEPEI — proposta de redução de tabelas

## Resultado

O diagrama original contém 40 tabelas: 29 do domínio `core` e 11 de autenticação/auditoria do Django. A proposta consolidada contém 25 tabelas, mantendo um único grupo por usuário.

## Consolidações

- `planartifact`, `strategicaction`, `strategictarget` e `criticalsuccessfactor` → `plan_item`, discriminado por `kind`.
- `activityblocker` e `activityevidence` → `activity_record`, discriminado por `kind`.
- As três tabelas N:N de indicadores → `indicator_link`, discriminado por `link_kind`.
- Os seis subtipos de registros de risco → `risk_event`, discriminado por `kind`.
- `sectorreport` e `quarterlysectorreport` → `report`, discriminado por `kind`.
- `report_cycle_unit` foi removida; a unidade participante é identificada diretamente em `report`.
- O prazo obrigatório de envio foi removido de `report_cycle`; permanecem apenas as datas do período de referência.
- `audit_log` e `notification` permanecem separadas por terem ciclos de vida distintos.
- `plan_link` registra relações opcionais entre elementos de planos.
- Autorização simplificada: cada usuário possui um `group_id` e cada permissão possui um `group_id`; as tabelas intermediárias de autenticação são removidas.
- A hierarquia entre unidades foi removida; `organizational_unit` mantém apenas o vínculo direto com a organização.

## Garantia de preservação

Nenhuma coluna de negócio foi descartada: os campos específicos permanecem como colunas opcionais nas tabelas consolidadas. A migração deve copiar os `id`s originais, preencher `kind`/`link_kind` com o subtipo antigo e criar views compatíveis com os nomes legados durante a transição. A regra de autorização passa a ser um usuário em um grupo, sem permissões individuais.

## Regras necessárias

1. `kind` deve ser enum/check constraint; cada subtipo deve aceitar apenas seus campos específicos.
2. `indicator_link` precisa de constraints condicionais para garantir uma única coluna de destino conforme `link_kind`.
3. `risk_event` deve exigir os campos mínimos conforme `kind` e manter os vínculos de usuário/unidade existentes.
4. Criar índices únicos equivalentes aos existentes, especialmente em códigos, relações N:N e combinações ano/trimestre/plano/unidade.
5. Manter views de compatibilidade até que o código da aplicação seja atualizado e validado.

O arquivo `GEPEI-minimo.dbml` contém o novo diagrama lógico consolidado e pode ser colado diretamente no dbdiagram.io.
