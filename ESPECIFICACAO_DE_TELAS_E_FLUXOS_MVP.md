# Especificação de Telas e Fluxos — MVP

**Versão:** 0.1  
**Data:** 28 de julho de 2026  
**Piloto:** COPIN e SRH

## 1. Objetivo

Definir as telas essenciais e os fluxos de uso do MVP para orientar o protótipo funcional e a implementação.

## 2. Navegação principal

| Área | Perfis principais | Finalidade |
|---|---|---|
| Painel | COPIN, chefia, visualizador | Visualizar situação estratégica e pendências. |
| PEI | COPIN, chefia, visualizador | Navegar por dimensões, eixos, objetivos, projetos, ações, metas e indicadores. |
| Plano de ação | COPIN, chefia, pessoa executora | Gerir atividades, pessoas executoras, entregas, recursos, dependências e evidências. |
| Mapa de riscos | COPIN, chefia, pessoa executora | Identificar, avaliar, tratar e acompanhar riscos. |
| Indicadores | COPIN e responsáveis autorizados | Registrar aferições e acompanhar metas. |
| Relatórios | COPIN, chefia e validador | Preparar, validar, consolidar e exportar ciclos de relatório. |
| Administração | Administrador e COPIN autorizada | Gerir usuários, unidades, permissões e configurações. |

## 3. Tela 1 — Acesso

### Finalidade

Permitir o acesso de usuários autorizados com endereço Gmail e senha.

### Elementos

- campo de e-mail;
- campo de senha;
- recuperação de senha;
- mensagem de acesso bloqueado ou não autorizado;
- aceite de termos institucionais quando necessário.

### Regras

- usuário inativo não acessa;
- após autenticação, o sistema carrega perfis e escopos de unidade;
- primeiro acesso pode exigir troca de senha.

## 4. Tela 2 — Painel COPIN

### Finalidade

Entregar visão consolidada da situação do PEI e do ciclo de acompanhamento.

### Componentes

- filtros: plano, objetivo, órgão/setor, período, status e fonte de recurso;
- metas e indicadores em atenção;
- ações atrasadas, bloqueadas ou sem atualização;
- riscos altos, muito altos ou materializados;
- andamento de relatórios setoriais;
- execução financeira manual, quando aplicável;
- lista de prioridades com responsável e próximo prazo.

### Ações

- abrir objetivo, ação, atividade, risco ou relatório a partir de qualquer alerta;
- exportar visão filtrada;
- iniciar ou acompanhar ciclo de relatório.

## 5. Tela 3 — Exploração do PEI

### Finalidade

Permitir navegação da estratégia até os elementos executáveis.

### Componentes

- árvore ou trilha: Dimensão BSC → Eixo → Objetivo → Projeto → Ação;
- descrição, responsável, prazo e status do item selecionado;
- metas e indicadores relacionados;
- ações estratégicas vinculadas;
- visão de riscos, pendências e evidências relacionadas.

### Ações

- COPIN cadastra, importa ou revisa artefatos;
- usuários autorizados abrem o plano de ação de uma Ação Estratégica;
- revisões formais criam nova versão, preservando a anterior.

## 6. Tela 4 — Ação Estratégica e Plano de Ação

### Finalidade

Gerir a execução operacional de uma Ação Estratégica.

### Cabeçalho da ação

- título, código, prazo, status e percentual de execução;
- unidade coordenadora;
- setores participantes;
- metas, indicadores e projeto relacionados;
- resumo de riscos, recursos e pendências.

### Lista de atividades

Cada atividade exibe:

- título;
- pessoa executora atribuída;
- peso e percentual;
- prazo e status;
- entrega ou produto esperado;
- dependências;
- sinalização de risco e evidências.

### Ações permitidas

- chefia/responsável de gestão cria atividades e atribui pessoa executora;
- pessoa executora atualiza a própria atividade;
- COPIN acompanha e, quando autorizado, corrige com trilha de auditoria;
- pesos devem totalizar 100%; 
- prazo vencido muda o status automaticamente para atrasada.

## 7. Tela 5 — Atualização de atividade

### Finalidade

Registrar o andamento contínuo da execução, antes do ciclo de relatório.

### Campos

- status;
- percentual de execução;
- comentário de progresso;
- dificuldades ou barreiras;
- risco identificado ou materializado;
- previsão de conclusão;
- entrega ou produto realizado;
- recursos utilizados;
- anexos e referências SEI.

### Regras

- impedimentos e riscos são registrados quando ocorrem;
- campos adicionais são apresentados conforme a situação escolhida;
- atualização registra data/hora e autor;
- campos críticos alterados pela COPIN preservam valor anterior, novo valor e justificativa.

## 8. Tela 6 — Mapa de riscos

### Finalidade

Controlar riscos do plano de ação, da ação estratégica, do projeto ou da atividade.

### Lista de riscos

- risco, item afetado, responsável e situação;
- probabilidade, impacto e nível pela matriz 5 x 5;
- decisão de tratamento;
- prazo de medida preventiva;
- alerta de risco alto, muito alto ou materializado.

### Formulário de risco

- identificação, descrição, categoria e causas;
- item afetado e pessoa responsável;
- probabilidade e impacto;
- avaliação opcional de risco inerente e residual;
- necessidade de tratamento;
- resposta: aceitar, mitigar, evitar ou transferir;
- medidas preventivas, responsável e prazo;
- medida de contingência;
- situação e registro de materialização.

### Ações

- registrar aceite conforme matriz de alçadas;
- anexar evidências;
- disparar alerta à COPIN quando aplicável;
- registrar providências de materialização.

## 9. Tela 7 — Indicadores e metas

### Finalidade

Cadastrar, aferir e acompanhar indicadores estratégicos.

### Componentes

- fórmula, unidade, fonte, linha de base, periodicidade e responsável;
- metas/objetivos associados;
- histórico por período;
- tendência e semáforo;
- evidência ou fonte de cada aferição.

### Ações

- COPIN cadastra ou revisa indicador;
- responsável autorizado registra aferição;
- sistema recalcula situação conforme regra do indicador.

## 10. Tela 8 — Ciclo e relatório setorial

### Finalidade

Transformar atualizações contínuas em prestação de contas do período.

### Etapas

1. COPIN abre ciclo e define período, participantes e data-limite.
2. O setor revisa dados reunidos automaticamente.
3. O responsável pelo relatório adiciona síntese, complementos e necessidade de decisão da gestão.
4. O setor envia o relatório a um validador designado.
5. O validador aprova ou devolve para correção.
6. A COPIN consolida relatórios aprovados.
7. O fechamento preserva fotografia dos dados e bloqueia alterações comuns.

### Conteúdo automático

- ações e atividades do setor;
- status, atrasos e bloqueios;
- entregas/evidências;
- riscos e materializações;
- recursos e execução financeira, quando aplicável;
- indicadores e metas relacionados;
- itens sem atualização.

### Regra de segregação

Quando a chefia for pessoa executora de atividade incluída no relatório, o sistema exige validador alternativo, como gestor superior ou COPIN.

## 11. Tela 9 — Consolidação COPIN

### Finalidade

Consolidar relatórios setoriais para CGPEI, CGGE ou Secretário.

### Componentes

- situação de envio e validação por setor;
- pendências e devoluções;
- visão consolidada de metas, ações, riscos, recursos e barreiras;
- comentários técnicos da COPIN;
- geração de documento consolidado.

### Ações

- devolver relatório setorial com comentário e novo prazo;
- consolidar apenas relatórios aprovados ou registrar exceção;
- exportar relatório em PDF, Excel e Word;
- encerrar ciclo.

## 12. Tela 10 — Administração

### Finalidade

Manter a base institucional e as regras de acesso do piloto.

### Componentes

- usuários e status de acesso;
- organizações, unidades e setores;
- perfis e permissões;
- tipos de plano e artefato;
- categorias de risco e matriz 5 x 5;
- ciclos de relatório;
- limite e tipos de arquivo permitidos.

## 13. Fluxos prioritários para implementação

1. Administrador cria usuário, unidade e perfil.
2. COPIN importa/publica PEI e cadastra Ação Estratégica.
3. Chefia cria plano de ação, atividades e atribui pessoas executoras.
4. Pessoa executora atualiza atividade, entrega, recurso, evidência e risco.
5. COPIN monitora painel e recebe alerta.
6. COPIN abre ciclo de relatório; setor envia; validador aprova/devolve; COPIN consolida.
7. COPIN exporta relatório e encerra o ciclo.

## 14. Próximas decisões de design

1. Definir o estilo visual institucional do sistema: cores, logotipo e nome de trabalho.
2. Definir a nomenclatura dos cinco níveis da matriz de risco.
3. Definir regras numéricas de semáforo de metas, indicadores e orçamento.
4. Validar a primeira versão dos fluxos com COPIN e SRH antes de iniciar a construção funcional.
