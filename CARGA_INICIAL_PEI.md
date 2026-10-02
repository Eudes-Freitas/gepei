# Carga Inicial do PEI — GEPEI

**Fonte primária:** `Diagramação - Plano Estratégico 20252034 - SESED (1).pdf`  
**Plano:** Plano Estratégico Institucional da SESED, 2025–2034  
**Situação:** preparação de carga - versão canônica confirmada

## 1. Escopo da carga

O GEPEI utilizará o arquivo estruturado do PEI como fonte principal da carga inicial. A importação abrangerá somente os elementos que podem ser monitorados e executados pela plataforma:

```text
Dimensão BSC
  → Eixo estratégico
    → Objetivo estratégico
      → Projeto estratégico
        → Ação estratégica
          → Meta
            → Indicador e aferições futuras
```

Também serão capturados, quando existirem no documento:

- unidade coordenadora e demais unidades participantes;
- fonte de recursos;
- fatores críticos de sucesso;
- prazos e periodicidades;
- responsáveis pela aferição;
- descrição e fórmula de indicadores;
- linhas de base e metas.

## 2. Itens deliberadamente fora da carga inicial

- texto histórico, metodológico e bibliográfico;
- imagens e elementos meramente ilustrativos;
- minuta e conteúdo de governança do anexo, pois não representam a versão vigente;
- referências normativas que não precisem ser vinculadas a uma ação, meta ou indicador.

Esses itens poderão ser preservados como documento-fonte ou evidência, sem se tornarem cadastros operacionais.

## 3. Método de importação

1. Extrair os elementos estruturais do arquivo para uma área de revisão.
2. Validar códigos, nomenclaturas, responsáveis e vínculos com a COPIN.
3. Publicar os elementos validados no PEI do GEPEI.
4. Criar planos de ação operacionais somente após a publicação das Ações Estratégicas.
5. Registrar alterações posteriores como revisão formal, sem sobrescrever a versão carregada.

## 4. Validação da fonte

O PDF diagramado 2025-2034 foi confirmado como a fonte canônica. Ele apresenta a
vigência de 2025 a 2034 na seção 12.1, página 34, e não possui ocorrências de 2035.

O arquivo auxiliar `Plano Estratégico SESED.docx.pdf`, que contém referências a 2035,
fica excluído da carga. O anexo de governança do documento canônico também permanece
fora da carga, pois sua atualização já foi apontada como necessária.

## 5. Modelo mínimo necessário antes da carga completa

A estrutura Python já contém organização, unidades, plano, artefato, ação estratégica,
plano de ação, atividade, risco, metas, indicadores, aferições e fatores críticos de
sucesso. Antes da carga completa, ainda serão concluídos:

- fontes de recurso e fatores críticos de sucesso;
- histórico/versionamento da estrutura do PEI.

## 6. Critério de aceite da carga

A carga será considerada pronta para o piloto quando a COPIN puder navegar do PEI até cada Ação Estratégica, consultar metas e indicadores associados e iniciar a atribuição de atividades ao SRH sem depender de planilhas paralelas.

## 7. Situação da carga estrutural

**Concluída em ambiente local:** o portfólio completo do PEI foi registrado a partir
do Apêndice B do PDF diagramado, abrangendo as dimensões BSC, os 9 eixos, os 13
objetivos estratégicos, seus projetos, ações estratégicas, metas, indicadores,
unidades responsáveis e fatores críticos de sucesso.

| Elemento | Registros publicados |
|---|---:|
| Objetivos estratégicos | 13 |
| Ações estratégicas | 39 |
| Metas | 37 |
| Indicadores | 37 |
| Fatores críticos de sucesso | 49 |

### Pendências de enriquecimento

- fórmulas de cálculo, finalidade, fonte de dados e linha de base de cada indicador,
  constantes do Apêndice A;
- valores de aferição iniciais e históricos;
- cronogramas operacionais, responsáveis individuais e atividades/tarefas;
- vínculos com PESP, PPA e os demais instrumentos de planejamento.

Os prazos das ações estratégicas foram mantidos em branco quando não constavam do
PEI. Eles deverão ser definidos no plano de ação operacional, sem serem confundidos
com a vigência geral do plano.
