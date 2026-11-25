"""Matrizes de responsabilidades do PESP/RN 2022–2031, pp. 74–99."""

# Cada linha registra número, título, órgãos, objetivos específicos e referências a metas.
ACTIONS = ((1,
  'Adotar medidas de redução aos crimes violentos letais intencionais, às mortes por intervenção legal de '
  'agentes do Estado e crimes contra o patrimônio.',
  ('SESED', 'SEAP', 'PMRN', 'PCRN', 'PPRN', 'CBMRN', 'PCIRN', 'COPDEC'),
  ('I', 'II', 'IV', 'V', 'XI', 'XVI', 'XXIII'),
  'Todas'),
 (2,
  'Adotar medidas de melhoria do controle de armas, munições e acessórios bélicos apreendidos, bem como do '
  'controle patrimonial das utilizadas pelas forças de segurança.',
  ('SESED', 'SEAP', 'PMRN', 'PCRN', 'PPRN', 'CBMRN', 'PCIRN', 'COPDEC'),
  ('I', 'II', 'IV', 'XVI'),
  ('01', '03', '07', '09')),
 (3,
  'Reduzir todas as formas de violência contra meninas e mulheres, qualificar e humanizar o atendimento e o '
  'acolhimento de vítimas.',
  ('SESED', 'SEAP', 'PMRN', 'PCRN', 'PPRN', 'CBMRN', 'PCIRN'),
  ('II',),
  ('01', '02', '03', '09')),
 (4,
  'Identificar e definir estratégias para redução da violência não letal que incida sobre segmentos '
  'vulnerabilizados da população.',
  ('SESED', 'SEAP', 'PMRN', 'PCRN', 'PPRN', 'CBMRN', 'PCIRN', 'COPDEC'),
  ('II', 'III'),
  ('04', '05')),
 (5,
  'Fortalecer as atividades de Proteção e Defesa Civil, incluindo ações de urgência e emergência, assegurando '
  'ações de prevenção, intervenção em desastres, atendimento aos incidentes e de preservação ambiental.',
  ('SESED', 'SEAP', 'PMRN', 'PCRN', 'PPRN', 'CBMRN', 'PCIRN', 'COPDEC'),
  ('X',),
  ('16',)),
 (6,
  'Modernizar os critérios de emprego do efetivo e das modalidades de atuação dos órgãos do SISPRN.',
  ('SESED', 'SEAP', 'PMRN', 'PCRN', 'PPRN', 'CBMRN', 'PCIRN', 'COPDEC'),
  ('XI', 'XIII', 'XV'),
  ('07',)),
 (7,
  'Aprimorar a gestão do sistema penitenciário estadual e implementar programas voltados à reinserção social '
  'dos egressos.',
  ('SEAP', 'PPRN'),
  ('I', 'II', 'VI', 'VII', 'VIII', 'XIV'),
  ('01', '02', '03', '09', '11', '12', '13', '17')),
 (8,
  'Fortalecer a gestão de pessoas dos órgãos do SISPRN.',
  ('SESED', 'SEAP', 'PMRN', 'PCRN', 'PPRN', 'CBMRN', 'PCIRN', 'COPDEC'),
  ('I', 'II', 'III', 'V', 'XII', 'XVIII'),
  ('01', '02', '03', '09', '11', '14', '17', '18')),
 (9,
  'Garantir estruturas físicas, equipamentos, materiais e insumos essenciais ao funcionamento do sistema de '
  'segurança pública.',
  ('SESED', 'SEAP', 'PMRN', 'PCRN', 'PPRN', 'CBMRN', 'PCIRN', 'COPDEC'),
  ('XIV', 'XVI'),
  ('12', '15', '20')),
 (10,
  'Desenvolver ações para garantir a valorização profissional, a qualidade de vida, a saúde e a segurança no '
  'trabalho dos operadores de segurança pública.',
  ('SESED', 'SEAP', 'PMRN', 'PCRN', 'PPRN', 'CBMRN', 'PCIRN', 'COPDEC'),
  ('XVI', 'XVIII', 'XIX'),
  ('14', '17', '18')),
 (11,
  'Ampliar a proteção dos profissionais de segurança, reduzir os índices de vitimização e acidentes em '
  'serviço.',
  ('SESED', 'SEAP', 'PMRN', 'PCRN', 'PPRN', 'CBMRN', 'PCIRN', 'COPDEC'),
  ('XVI', 'XVIII'),
  ('14', '17', '18')),
 (12,
  'Atualizar as normas disciplinares e assegurar o tratamento digno aos profissionais de segurança pública.',
  ('SESED', 'SEAP', 'PMRN', 'PCRN', 'PPRN', 'CBMRN', 'PCIRN', 'COPDEC'),
  ('XIX',),
  ('19',)),
 (13,
  'Fortalecer o sistema de controle interno, de correição e de ouvidoria, bem como os canais de comunicação '
  'com a sociedade, nos órgãos que compõem o SISPRN.',
  ('SESED', 'SEAP', 'PMRN', 'PCRN', 'PPRN', 'CBMRN', 'PCIRN', 'COPDEC'),
  ('XV', 'XXII'),
  ('19', '20', '21')),
 (14,
  'Aprimorar os processos de segurança pública, especialmente os relacionados à fiscalização e/ou vistoria '
  'preventiva, policiamento ostensivo, perícia, investigação e inteligência, com inovação tecnológica e '
  'integração de sistemas de informação e comunicação.',
  ('SESED', 'SEAP', 'PMRN', 'PCRN', 'PPRN', 'CBMRN', 'PCIRN', 'COPDEC'),
  ('XIII',),
  'Todas'),
 (15,
  'Aprimorar a gestão da Secretaria de Estado da Segurança Pública e da Defesa Social (SESED) de modo a '
  'contribuir com a melhoria dos resultados do SISPRN.',
  ('SESED', 'SEAP', 'PMRN', 'PCRN', 'PPRN', 'CBMRN', 'PCIRN', 'COPDEC'),
  ('XV', 'XX'),
  ('15', '19', '20', '21')),
 (16,
  'Assegurar a participação social no controle da Política Estadual de Segurança Pública e Defesa Social.',
  ('SESED',),
  ('XXII',),
  ('21',)))

OBJECTIVES = {'I': 'reduzir homicídios e outros crimes violentos letais, especialmente, contra a juventude negra',
 'II': 'reduzir todas as formas de violência contra meninas e mulheres, qualificar e humanizar o atendimento e '
       'o acolhimento de vítimas',
 'IV': 'instituir programa estadual de controle de armas de fogo, munições e acessórios bélicos apreendidos',
 'V': 'fortalecer mecanismos de enfrentamento à violência no trânsito, bem como prevenir e reduzir os crimes '
      'patrimoniais, em especial os violentos, e ampliar a sensação de segurança da população',
 'XI': 'atualizar os marcos normativos estruturantes do SISP/RN e modernizar os critérios de emprego do '
       'efetivo e dos modais de atuação dos órgãos de segurança pública',
 'XVI': 'ampliar a proteção dos profissionais de segurança e reduzir os índices de vitimização e acidentes em '
        'serviço',
 'XXIII': 'fortalecer o combate ao crime organizado, estruturando as instituições, conferindo a devida '
          'autonomia funcional',
 'III': 'identificar e definir estratégias para redução da violência não letal decorrente de discriminação por '
        'razões raciais, religiosas, de orientação sexual e identidade de gênero, de condição de pessoa com '
        'deficiência e que incida sobre segmentos vulnerabilizados da população',
 'X': 'fortalecer as atividades de proteção e defesa civil, assegurando ações de prevenção e intervenção em '
      'desastres e de preservação ambiental',
 'XIII': 'aprimorar os processos de segurança pública, especialmente os relacionados às perícia criminal e '
         'inteligência, com inovação tecnológica e integração de sistemas de informação e comunicação',
 'XV': 'fortalecer o sistema de controle interno dos órgãos de segurança e a ouvidoria de polícia',
 'VI': 'atuar em interface com o sistema socioeducativo para garantir a integridade patrimonial e a proteção '
       'dos socioeducandos',
 'VII': 'Aprimorar a gestão do sistema penitenciário através do fortalecimento da polícia penal, garantindo a '
        'sua estrutura organizacional',
 'VIII': 'criar novas vagas, garantindo o respeito aos direitos das pessoas em privação de liberdade e a todos '
         'os envolvidos no sistema prisional e de segurança, promovendo a implementação de programas de '
         'reinserção social dos egressos',
 'XIV': 'assegurar a renovação periódica e a manutenção de equipamentos e estruturas essenciais ao '
        'funcionamento do sistema de segurança pública, mediante consulta prévia junto aos operadores e '
        'instituições quanto à adequação dos bens a serem adquiridos para as atividades do SISPRN',
 'XII': 'recompor o efetivo dos órgãos de segurança e desenvolver programas de formação, capacitação e '
        'qualificação permanente dos profissionais',
 'XVIII': 'assegurar o atendimento de saúde, em especial no Hospital da Polícia Militar, e a realização de '
          'atividades periódicas de qualificação e atualização dos profissionais de segurança',
 'XIX': 'atualizar as normas disciplinares aplicáveis aos profissionais integrantes do SISPRN, especialmente '
        'para abolir penalidades que impliquem em privação de liberdade',
 'XXII': 'assegurar a participação social na elaboração e no controle da política e das estratégias de '
         'segurança pública, mediante a criação de sistema de órgãos colegiados',
 'XX': 'reforçar o papel de gestora da Secretaria de Estado da Segurança Pública e da Defesa Social (SESED) e '
       'implementar estratégias de gestão para resultados no SISPRN'}
