# Dados fictícios para validar relatórios

Carga aplicada em 22/10/2026, para os quatro trimestres de 2026, no PEI existente.

Todos os registros novos com texto identificador e todos os arquivos gerados usam **[TESTE]**. Os nomes e os vínculos oficiais dos objetivos, ações, metas, indicadores e setores foram preservados. Planos de ação que não possuem nome próprio são identificados pelo manifesto da carga.

| Dados novos | Quantidade |
| --- | ---: |
| Atividades | 210 |
| Evidências de atividade, com arquivo | 156 |
| Aferições, com arquivo | 148 |
| Riscos, avaliações e tratamentos | 39 de cada |
| Planos de ação antes inexistentes | 30 |
| Relatórios trimestrais novos | 58 |

Os dois relatórios existentes foram atualizados, com as versões anteriores preservadas. Agora há 60 relatórios de 2026: quatro trimestres para 15 setores. Os relatórios que contêm testes estão identificados com **[TESTE]** na lista.

As atividades simulam entregas concluídas, em execução e parciais. A pedido da usuária, as 39 atividades de teste antes não iniciadas foram atualizadas para 40% e em andamento. A situação e o percentual de execução das ações foram recalculados a partir das atividades. Na revisão seguinte, a quantidade foi variada para 3 a 8 atividades [TESTE] por ação, totalizando 210, com percentuais de execução distribuídos por toda a escala. As atividades originais e seus pesos foram preservados. Não foram mantidos impedimentos de teste nem usuário fictício. Os cadastros do plano original, seus objetivos, ações, metas, indicadores e vínculos foram preservados; somente a execução foi atualizada conforme solicitado. O peso disponível de cada plano foi distribuído entre as novas atividades, sem alterar os pesos existentes. Se o plano já totalizava 100%, as atividades de teste recebem peso zero.

As aferições apresentam valores fictícios de planejamento e execução em cada trimestre. Cada indicador aparece junto das metas efetivamente vinculadas, do resultado e do gráfico de evolução até o final do trimestre. As tabelas de aferições e os arquivos de evidência respeitam o trimestre selecionado. As contagens continuam considerando o setor e sua participação em outras unidades, sem duplicação dentro do relatório.

## Consultar

Em **Relatórios**, escolha o setor e o período. Por exemplo, COPIN, 3º trimestre de 2026: 9 metas, 9 indicadores e 11 evidências de atividade. Os anexos podem ser abertos na seção de evidências e nas aferições dos indicadores.

## Repetir ou remover

A carga é idempotente: repetir o comando não duplica os registros.

```bash
venv/bin/python manage.py load_test_execution --year 2026
```

Para remover somente os registros desta carga, seus arquivos e relatórios novos, restaurando os relatórios anteriores:

```bash
venv/bin/python manage.py load_test_execution --year 2026 --remove
```

A remoção usa os IDs registrados em `.test-data/pei-2026.json`; preserve esse manifesto. Ela restaura as cópias anteriores dos relatórios que a carga atualizou. Relatórios consolidados manualmente depois da carga devem ser refeitos após a remoção, para atualizar suas cópias dos dados.

Backup anterior à carga: `/tmp/gepei-before-test-data-20261022-163452.sqlite3`.

## Verificação

Os testes direcionados passaram, incluindo repetição sem duplicação, remoção dos arquivos, preservação dos dados existentes, vínculos entre metas e indicadores, evidências e impedimentos. Na base preenchida, os 60 relatórios responderam corretamente; seus 344 blocos de indicador têm metas vinculadas e gráficos. Downloads de evidências de atividade e aferição foram conferidos e contêm a identificação [TESTE].

## Variação das atividades e das cores

```bash
venv/bin/python manage.py vary_test_execution --year 2026
```

Esse comando varia somente as atividades listadas no manifesto de teste, preserva seus vínculos com riscos e evidências e atualiza a execução e os relatórios. Foram conferidas 14 cores distintas na base: a escala contínua passa por vermelho, laranja, amarelo, verde claro e verde, conforme o percentual executado. A quantidade de atividades não define a cor; o cálculo considera o percentual executado e o peso de cada atividade.

A revisão passou em três testes, incluindo preservação das atividades originais, repetição sem duplicação, continuidade das cores e remoção da carga. As visualizações em colunas e listagem e os 60 relatórios foram conferidos.

## Linhas de base documentais

As bases de 2024 e projeções de 2025 a 2034 foram preenchidas com DADOS INDICADORES.pdf. São dados de referência documentais, preservados ao remover os resultados de teste. As 148 aferições de teste e seus anexos foram recalibrados; a repetição da carga passa a respeitar esses parâmetros. Os arquivos de evidência antigos foram mantidos para as versões anteriores dos relatórios.

Consulte [a auditoria das bases](AUDITORIA_BASES_INDICADORES.md).
