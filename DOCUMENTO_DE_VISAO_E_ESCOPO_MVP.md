# Plataforma de Gestão Integrada da Estratégia

## Documento de Visão do Produto e Escopo do MVP

**Versão:** 0.1  
**Data:** 18 de julho de 2026  
**Organização-piloto:** Secretaria de Estado da Segurança Pública e da Defesa Social (SESED/RN)

## 1. Visão do produto

Construir uma plataforma web de gestão integrada da estratégia que conecte a execução cotidiana de servidores, setores, órgãos executores e parceiros às metas, objetivos e demais instrumentos de planejamento da SESED. A plataforma deve fornecer dados confiáveis e atualizados para a COPIN, gestores e órgãos de controle, permitindo acompanhar resultados, responsabilidades, riscos, orçamento, evidências e gargalos em um único ambiente.

O produto não substituirá o SEI para fluxos formais de despachos e processos. Seu papel será organizar o monitoramento, a consolidação de dados, os alertas, as evidências e a geração de relatórios, com referências a processos SEI quando aplicável.

## 2. Problema a resolver

Atualmente, informações sobre planejamento e execução estão distribuídas entre planilhas, reuniões e documentos. Isso reduz a capacidade de resposta sobre metas, planos de ação, responsáveis, recursos executados e barreiras à execução.

O problema central é a desconexão entre o trabalho realizado nos setores e a visão estratégica necessária à tomada de decisão. A COPIN precisa consolidar manualmente informações para produzir relatórios e responder a gestores e órgãos de controle.

## 3. Proposta de valor

Uma única ferramenta para integrar planos, objetivos, ações, metas, indicadores, recursos financeiros, riscos e evidências. Uma mesma ação poderá contribuir para mais de um instrumento de planejamento, com regras explícitas de relacionamento e peso de contribuição.

O sistema deverá responder, de forma tempestiva, a perguntas como:

- Qual a situação dos objetivos e metas de cada plano?
- Quais ações estão atrasadas, bloqueadas ou sem atualização?
- Quem é responsável e quais barreiras impedem a execução?
- Quais riscos se materializaram e como estão sendo tratados?
- Que recursos foram previstos, empenhados, liquidados e pagos?
- Quais ações contribuem simultaneamente para PEI, PESP, PPA e outros planos?

## 4. Público e piloto

### Usuários do piloto

- COPIN;
- FUNSEP;
- CTINF;
- CPCID;
- CODIMM;
- CIOSP.

O piloto deverá atender menos de 30 usuários, com expansão posterior para todos os setores da SESED e os órgãos conveniados: Polícia Militar, Polícia Civil, Corpo de Bombeiros e Polícia Científica.

### Perfis de acesso

| Perfil | Responsabilidades principais |
|---|---|
| Administrador | Gerenciar usuários, órgãos, setores, planos e permissões. |
| COPIN | Monitorar o conjunto dos planos, consolidar dados, acompanhar indicadores, corrigir informações com auditoria e emitir relatórios. |
| Chefia de setor/órgão | Acompanhar e validar a execução de sua unidade; alterar prazo, responsável, meta ou escopo, com registro. |
| Responsável por ação | Atualizar ações, execução, evidências, riscos, custos, dificuldades e previsão de conclusão. |
| Visualizador | Consultar painéis e relatórios conforme a permissão atribuída. |

Os perfis autorizados poderão visualizar ações de outros setores quando estas contribuírem para os mesmos objetivos ou metas.

## 5. Governança apoiada pela plataforma

```text
Responsável / setor
  atualiza execução, evidências, riscos e dificuldades
        ↓
Chefia imediata e COPIN
  acompanham e validam a consistência das informações
        ↓
COPIN
  consolida dados, monitora indicadores e produz relatórios
        ↓
CGPEI
  supervisiona e valida relatórios e propostas de atualização
        ↓
CGGE
  acompanha a estratégia e aprova revisões e relatórios estratégicos
```

O trâmite documental formal e a comunicação por despachos permanecem no SEI. A plataforma poderá armazenar referências ou links para processos SEI e anexar documentos que sustentem registros ou mudanças de rota.

## 6. Escopo funcional do MVP

### 6.1 Planos e artefatos

O MVP deverá cadastrar e relacionar inicialmente:

- PEI;
- PESP;
- PPA;
- Plano de Enfrentamento à Violência contra a Mulher;
- Plano de Melhorias do IMGG (SEPLAN);
- Plano de Integridade e Compliance (CONTROL);
- Plano de Ação da Auditoria IGOV_SEG (TCE).

O PEI será o primeiro plano integralmente importado, cadastrado e testado. PESP e PPA poderão ter hierarquias próprias e mais robustas. Os demais planos poderão ser estruturados de forma leve, vinculando-se diretamente a ações ou iniciativas.

Estrutura de referência do PEI:

```text
Dimensão BSC → Eixo Estratégico → Objetivo Estratégico
  → Projeto Estratégico → Ação Estratégica → Meta → Indicador
```

Cada plano poderá usar sua própria estrutura de artefatos.

### 6.2 Ações

Cada ação deverá conter, no mínimo:

- unidade responsável coordenadora;
- setores ou órgãos participantes, quando houver;
- prazo;
- percentual de execução;
- status;
- evidências;
- custo e dados financeiros, quando aplicáveis;
- riscos;
- observações, dificuldades e justificativas.

As unidades organizacionais serão estruturadas hierarquicamente, por exemplo: SESED → órgão ou unidade → setor. Cada ação terá um setor ou órgão responsável principal, podendo envolver colaboradores de outras unidades.

Há duas camadas de execução:

- **Ação estratégica:** artefato estável do plano, alterado somente nas revisões ordinárias ou formais do instrumento de planejamento. Possui uma unidade coordenadora e, quando aplicável, setores participantes;
- **Plano de ação operacional:** conjunto de atividades ou tarefas criado e mantido pelos usuários para executar a ação estratégica, meta ou objetivo. Cada atividade é atribuída a uma pessoa executora.

O responsável poderá distribuir pesos ou níveis de esforço entre as atividades do plano de ação. O percentual da ação poderá ser informado manualmente, calculado a partir das atividades ponderadas, ou usar ambos os mecanismos conforme a configuração definida.

Cada atividade do plano de ação terá, no mínimo, título, descrição, pessoa executora atribuída, prazo, peso, status, recursos, entrega ou produto esperado, dependências e evidências. A atribuição será feita pela pessoa responsável pela gestão da ação estratégica, normalmente a chefia da unidade coordenadora. Uma atividade poderá depender de outra e receberá alertas para prazo próximo ou vencido. O status será atualizado automaticamente para atrasado quando ultrapassar seu prazo.

Os pesos das atividades de uma ação deverão sempre totalizar 100%. A conclusão de atividades ponderadas permitirá calcular o percentual de execução da ação. Atividades concluídas poderão ser reabertas para correção de registro indevido ou equivocado.

Recursos poderão ser registrados no nível da atividade, incluindo:

- financeiro, quando houver desembolso, com fonte de financiamento (FAF, convênio ou tesouro estadual);
- logístico, como espaço e infraestrutura;
- pessoal.

Cada atividade poderá registrar uma entrega ou produto esperado. Exemplos: minuta de portaria como entrega e portaria publicada como produto; ata de reunião como entrega. A evidência será obrigatória apenas quando a regra de controle ou a entrega prevista assim determinar.

Impedimentos, barreiras, riscos e dificuldades serão registrados pela pessoa executora da atividade no momento em que ocorrerem. O ciclo de relatório apenas reunirá esses registros, permitindo complemento ou contextualização pelo setor antes do envio.

Projetos estratégicos transversais poderão envolver múltiplas unidades participantes, um gestor de projeto designado e atividades atribuídas individualmente a pessoas executoras. O detalhamento da estrutura transversal será refinado em etapa posterior; a participação de outro setor não será tratada como suplência.

Status permitidos: **não iniciada, em andamento, concluída, atrasada, bloqueada e suspensa**.

Uma ação será classificada como atrasada apenas após ultrapassar seu prazo. Uma ação bloqueada exigirá motivo, responsável pela solução e previsão de desbloqueio. Ações concluídas poderão ser reabertas apenas para correção de registro indevido ou equivocado.

Ao ultrapassar o prazo, o sistema mudará automaticamente o status da ação para atrasada.

### 6.3 Indicadores, metas e aferições

Cada indicador terá:

- nome e descrição;
- fórmula;
- unidade de medida;
- fonte de dados;
- periodicidade definida no PEI;
- linha de base;
- meta;
- responsável pela aferição;
- valores históricos por período.

Uma meta poderá ter vários indicadores, e um indicador poderá medir mais de um objetivo. Os valores serão inseridos manualmente pela COPIN ou pelo setor responsável.

Semáforo inicial:

- verde: conforme ou melhor que o esperado;
- amarelo: atenção, abaixo do esperado mas recuperável;
- vermelho: situação crítica ou meta comprometida;
- cinza: dado insuficiente ou sem atualização.

### 6.4 Riscos

Categorias iniciais: orçamentário, operacional, jurídico, tecnológico, pessoas e externo.

O mapa de riscos fará parte do plano de ação e poderá ser vinculado à ação estratégica, projeto, atividade ou tarefa afetada. Cada risco deverá registrar, no mínimo:

- identificação e descrição;
- categoria;
- causas;
- artefato ou atividade afetada;
- pessoa responsável pelo acompanhamento;
- probabilidade e impacto;
- nível de risco, calculado pela matriz de probabilidade x impacto;
- avaliação da necessidade de tratamento;
- decisão de tratamento: aceitar, mitigar, evitar ou transferir;
- medidas preventivas e responsável por sua execução;
- medida de contingência para o caso de materialização;
- situação: identificado, em tratamento, materializado ou encerrado.

O risco será avaliado por matriz 5 x 5 de probabilidade e impacto. A nomenclatura dos cinco níveis será configurável. A aferição de controles, com registro de risco inerente e residual, será opcional: o usuário poderá identificar, analisar e avaliar um risco sem preencher essa etapa.

Riscos serão revisados a cada atualização da atividade ou conforme seu fluxo de realização. Riscos altos, muito altos ou materializados gerarão alerta automático à COPIN. A materialização não modificará automaticamente o status de ações, metas ou objetivos: o efeito dependerá do tratamento definido e das medidas adotadas ou deliberadamente não adotadas.

A aceitação de riscos seguirá matriz configurável de alçadas. Como referência inicial, a COPIN analisará tecnicamente riscos altos e muito altos, e o Secretário realizará a aceitação formal; o plano poderá prever manifestação ou participação de outros atores técnicos conforme a natureza do risco.

### 6.5 Financeiro

Para ações que possuam desembolso, registrar:

- orçamento previsto;
- valor empenhado;
- valor liquidado;
- valor pago;
- fonte de recurso;
- programa e ação orçamentária.

No MVP, os valores financeiros serão informados manualmente. A integração com sistema estadual poderá ser avaliada em evolução futura.

### 6.6 Vínculos e análise de impacto

Uma ação, meta, indicador, entrega ou recurso poderá se relacionar com artefatos de outros planos por vínculos diretos ou indiretos.

Tipos iniciais de vínculo:

- contribui para;
- financia;
- mede;
- executa;
- depende de;
- está alinhado a;
- é evidência de.

Cada vínculo poderá conter peso percentual. A tela da ação mostrará o vínculo principal de trabalho e todas as demais demandas, metas, indicadores e planos relacionados. Dependências entre ações deverão gerar alerta quando a ação predecessora atrasar.

### 6.7 Evidências e documentos

Cada evidência terá arquivo ou link/SEI, descrição, data e responsável pelo envio. Inicialmente, serão aceitos documentos PDF e imagens, com limite de tamanho configurável.

### 6.8 Relatórios, painéis e alertas

Relatórios indispensáveis no MVP:

- relatório trimestral por setor;
- relatório do PEI;
- visão de ações atrasadas, bloqueadas ou sem atualização;
- riscos materializados e tratamento definido;
- execução financeira;
- justificativas e barreiras ao avanço.

Os relatórios serão exibidos na plataforma e poderão ser exportados em PDF, Excel e Word. A geração de apresentação é uma evolução desejável.

Filtros essenciais: plano, objetivo, setor ou órgão responsável, período, status e fonte de recurso.

O painel da COPIN deverá apresentar, entre outros pontos:

- andamento de metas e objetivos por artefato, órgão, setor, responsável e período;
- execução das ações atribuídas;
- recursos executados por ação;
- status das ações;
- riscos e barreiras;
- destaque para PEI e PESP.

Alertas aparecerão no sistema e por e-mail para responsável, chefia imediata e COPIN. Haverá aviso, inicialmente, 15 dias antes do prazo de atualização necessário ao fechamento do relatório.

### 6.10 Ciclo de atualização e relatórios

O sistema deverá permitir ciclos trimestrais, quadrimestrais, semestrais e anuais, configuráveis por plano. As datas-limite serão definidas em conjunto para atender ao PEI ou a demandas de órgãos externos.

Fluxo do ciclo:

```text
COPIN configura o período e a data-limite
        ↓
Pessoa executora registra atualizações, barreiras, riscos e evidências ao longo do período
        ↓
Setor revisa e envia seu relatório do período
        ↓
Validador designado valida
        ↓
COPIN confere, devolve para correção se necessário, e consolida
        ↓
Relatório consolidado segue às instâncias superiores (CGPEI, CGGE ou Secretário)
```

Ao final, o período será bloqueado para alterações comuns e preservará uma fotografia dos dados daquele ciclo. Não será necessária assinatura formal dentro da plataforma; a versão final poderá ser encaminhada pelos meios institucionais, incluindo o SEI.

O relatório setorial deverá exigir, quando aplicável, resultados alcançados, dificuldades ou barreiras, riscos materializados, providências adotadas, próximos passos e necessidade de decisão da gestão. O relatório incluirá automaticamente ações sem atualização, atrasadas, bloqueadas ou suspensas.

O responsável pela preparação e envio do relatório será distinto do validador sempre que houver conflito de autoaprovação. Se a chefia do setor for executora de atividade incluída no relatório, o sistema exigirá um validador alternativo designado, como gestor superior ou COPIN. A validação final deverá registrar o usuário, data/hora e manifestação do validador.

### 6.9 Auditoria, revisões e orientações

Alterações feitas pela COPIN deverão registrar autor, data/hora, valor anterior, novo valor e justificativa. Alterações de prazo, responsável, meta ou escopo serão feitas pela chefia do setor/órgão e sinalizadas pelo sistema.

Planos, metas e indicadores revisados formalmente devem manter versões históricas. O histórico de acessos e alterações será guardado por até cinco anos.

O MVP incluirá uma área de orientações da COPIN para publicar tutoriais, manuais e modelos de relatório.

## 7. Premissas técnicas iniciais

- Aplicação web responsiva, para computador e celular.
- Autenticação inicial por conta e senha criada pelo administrador.
- Ambiente inicial de desenvolvimento e piloto em infraestrutura Firebase/Google.
- Arquitetura preparada para migração posterior à infraestrutura do Estado.
- Dados pessoais tratados apenas quando necessários, com controles de acesso apropriados antes do uso produtivo.
- Idioma: português.

## 8. Importação inicial

O arquivo estruturado `Plano Estratégico SESED.docx.md` será a fonte primária da carga inicial do PEI 2025–2034. A seção de governança presente no arquivo não será importada como regra vigente, pois requer atualização. Os demais artefatos originais servirão como fontes complementares. A importação seguirá três etapas:

1. envio de documentos e planilhas originais;
2. extração e mapeamento assistido de objetivos, projetos, ações, metas, indicadores, responsáveis e fontes de recursos;
3. revisão e publicação pela COPIN.

Nenhum dado extraído será considerado oficial antes da validação da COPIN.

## 9. Critérios de sucesso do piloto

O piloto será considerado bem-sucedido quando:

1. os setores participantes atualizarem ações e evidências sem depender de planilhas paralelas;
2. a COPIN consolidar o relatório trimestral diretamente na plataforma;
3. os gestores puderem identificar rapidamente execução, atrasos, riscos, recursos, responsáveis e gargalos;
4. os usuários participantes utilizarem o sistema com autonomia, apoiados por orientações simples.

## 10. Próximas etapas

1. Validar este documento de visão e escopo.
2. Detalhar o modelo de dados lógico e as regras de cálculo do semáforo.
3. Organizar backlog priorizado do MVP.
4. Desenhar protótipos das telas principais.
5. Definir a arquitetura técnica e o plano de implantação do piloto.
