param([switch]$Aplicar)
$ErrorActionPreference='Stop'
$root=[IO.Path]::GetFullPath((Join-Path $env:USERPROFILE 'Downloads\PDFs'))
$prefix=$root.TrimEnd('\')+'\'
function Normalize-Name($name) {
 $s=$name.Normalize([Text.NormalizationForm]::FormD)
 ([regex]::Replace($s,'\p{Mn}','')).ToLowerInvariant()
}
$rules=@(
 @('^artigo final v 1\.0','07 Estudos\TCC e metodologia científica\Sugestão de descarte','Possível versão anterior: existe Artigo Final V 2.0; comparar antes de excluir'),
 @('^plano a operacao petroleo.*v01','09 Trabalho\Planos de operações\Sugestão de descarte','Possível versão anterior: existe arquivo de nome semelhante marcado Final; comparar antes de excluir'),
 @('^sei','09 Trabalho\Processos SEI ofícios e relatórios','Documento administrativo SEI'),
 @('sala de descompressao|cap 8.*qvt','07 Estudos\Qualidade de vida e saúde no trabalho','Material sobre qualidade de vida no trabalho'),
 @('cloroquina|pos covid','02 Saúde\Estudos e informações de saúde','Material informativo sobre saúde'),
 @('planoepolticanacional|plano de trabalho ufrn|apres_1.*reuniao','09 Trabalho\Planejamento orçamento e projetos','Plano ou reunião de trabalho'),
 @('quadro de trabalho semanal','09 Trabalho\Escalas e quadros de trabalho','Quadro de trabalho'),
 @('ficha de inscricao|comprovante_inscricao|modelo para ficha de cadastro','07 Estudos\Inscrições e cadastros','Inscrição ou cadastro; finalidade ainda a conferir'),
 @('av_u3|os sete pecados da vale','07 Estudos\Aulas atividades e formulários','Atividade de curso'),
 @('revista.da.enit|desigualdade territorial','07 Estudos\Artigos e publicações - identificar tema','Publicação ou estudo'),
 @('customer_service','07 Estudos\Gestão organizações e inovação','Estudo sobre atendimento'),
 @('essenios','08 Religião e leituras\Bíblia teologia e reflexões','Material religioso'),
 @('comprovante de residencia|^endereco .*jesus','01 Pessoal\Residência\Sugestão de descarte','Comprovante de endereço: revisar se ainda tem utilidade; validade não conferida'),
 @('certidao.*(negativa|criminal|justica|estadual|tjrn|trabalhista|federal|corregedoria)|certidaonegativa|certidao-federal|certidao conjunta|certidaoconjunta','01 Pessoal\Certidões para cadastros\Sugestão de descarte','Certidão para finalidade pontual: conferir validade e necessidade antes de excluir'),
 @('certidao|certificado|diploma|historico_2017','01 Pessoal\Certificados diplomas e certidões permanentes','Documento pessoal ou comprovação de formação; preservar para análise'),
 @('cnh|^rg[ -]|^rg\d|^rg civil|^funcional |passaporte|situacao cadastral no cpf','01 Pessoal\Identificação','Documento de identificação'),
 @('casamento|wedding|convite neta|menu final','01 Pessoal\Casamento e cerimônia','Material de casamento ou cerimônia'),
 @('curriculo|curriculos','01 Pessoal\Currículos','Currículo'),
 @('tomografia|comparativo_exames|resultado_lab|laboratorio|hemolab|dna center','02 Saúde\Exames e análises','Histórico de saúde'),
 @('ortognatica|guiasolicitacao|guia_anexo_opme|sanidade','02 Saúde\Procedimentos e autorizações','Documento relacionado a procedimento de saúde'),
 @('unimed|amil|assofme|novo.vita','02 Saúde\Planos de saúde e contratos','Plano de saúde ou contrato'),
 @('irpf|informe de rendimentos|comprovante de rendimentos|report_ir|^darf|carne.leao|guia ir','03 Finanças\Imposto de renda e rendimentos','Documento fiscal; nome não basta para sugerir descarte'),
 @('binance|binace|historico_transacoes|cockpitcripto','03 Finanças\Criptomoedas - extratos e histórico','Histórico de investimentos'),
 @('cripto|bitcoin','03 Finanças\Criptomoedas - estudos e materiais','Material de estudo sobre investimentos'),
 @('spot|notanegociacao|day trade|xp operacoes|^negociacao|^_stvm','03 Finanças\Bolsa - notas e operações','Operações e notas de investimentos'),
 @('custodia|proventos|^posicao|^movimentacao|\d{11}-20\d\d-(anual|operacoes)|relatorio.*(anual|mensal)|accountstatement','03 Finanças\Bolsa - posições e relatórios','Posições e relatórios financeiros'),
 @('^extrato|^nu_\d|^banco do brasil|demonstrativo|^comprovante|^cob_|^fici_','03 Finanças\Extratos comprovantes e demonstrativos','Finalidade ou obrigação financeira não confirmada; revisar conteúdo'),
 @('cosern|neoenergia','03 Finanças\Contas de energia','Conta de consumo; conferir pagamento e utilidade como comprovante'),
 @('boleto|fatura|^relfat|itaucard|iptu|carne|nfse|^nota_','03 Finanças\Boletos faturas impostos e notas','Cobrança ou documento fiscal; conferir conteúdo'),
 @('embracon|portabilidade','03 Finanças\Consórcios e crédito','Consórcio ou crédito'),
 @('top.dividendos|release.*port|apresentacao [13]t20','03 Finanças\Análises e informes de mercado','Informação de mercado de período específico'),
 @('cadin','03 Finanças\Consultas cadastrais','Consulta cadastral financeira'),
 @('crlv|crve|codigoseguranca','04 Veículos e imóveis\Documentos de veículos','Documento de veículo; exercício e validade não conferidos'),
 @('vistiria|vistoria|chacaras|contrato residencial|titularidade','04 Veículos e imóveis\Imóveis e vistorias','Documento relacionado a imóvel ou vistoria'),
 @('contrato|distrato|procuracao|alegacoes|alvara|^08\d{5}|primeiras declaracoes|termo de declaracoes|processo semut','05 Jurídico\Contratos processos e procurações','Documento jurídico; preservar para análise'),
 @('voucher|^tickets-','06 Viagens e eventos\Reservas e ingressos\Sugestão de descarte','Possível uso pontual: confirmar se a viagem ou evento já aconteceu'),
 @('cotacao|tabela.gemini|varios objetos_coolers','06 Viagens e eventos\Cotações e ofertas\Sugestão de descarte','Cotação ou oferta: conferir se ainda está em uso'),
 @('calendario|cronograma 2021|qts atualizado|divisao dos grupos|grupos_noite|grupos_seminarios','07 Estudos\Agendas e grupos de cursos\Sugestão de descarte','Agenda ou distribuição de turma: conferir se o curso terminou'),
 @('tcc|pre.projeto|orientando|orientao|ficha_catalografica|normalizao|metodologia|pesquisa qualitativa|projetos de pesquisa|estudo_de_caso_como','07 Estudos\TCC e metodologia científica','Pesquisa e trabalho acadêmico'),
 @('qvt|qwlq|qualidade.*vida|qualidade|estresse|suicidio|cheremeta','07 Estudos\Qualidade de vida e saúde no trabalho','Tema de qualidade de vida no trabalho'),
 @('design thin|^dt modulo','07 Estudos\Design thinking e oficinas','Material de design thinking'),
 @('conhecimento|knowledge','07 Estudos\Gestão do conhecimento','Tema de gestão do conhecimento'),
 @('institucional|organizacional|inovacao|inovao|governanca|governana|new_public|gestao por processos|gestao de pessoas|lideranca|abordagem_human','07 Estudos\Gestão organizações e inovação','Tema de gestão e organizações'),
 @('analise.*discurso|analise.*conteudo|educacao e leitura','07 Estudos\Linguagem e análise do discurso','Tema de linguagem e análise'),
 @('ciencias policiais|ciclo completo|segurana.pblica','07 Estudos\Ciências policiais e segurança pública','Estudos de segurança pública'),
 @('artigo|\d+-.*-pb|dialnet|periodicos|journal|gerente.da.revista|^v17n|^salves|^admin,|anuario','07 Estudos\Artigos e publicações - identificar tema','Publicação cujo assunto não está claro no nome'),
 @('aula|curso|avali|atividade|unidade|^csp|eoc|ensino|question|seminario|guia.do.aluno|universidade|estudo de caso|estudo_de_caso|trabalho_modelo','07 Estudos\Aulas atividades e formulários','Material de curso ou atividade'),
 @('biblia|biblic|teologico|cristolog|igrejas|apocalipse|reflexao|pai nosso|plano divino|hagin|criacionismo|verdade e o engano|missionaria|paul_s|judaico|licao|licoes|adolescentes|ess.enios|greco.romano|integridade','08 Religião e leituras\Bíblia teologia e reflexões','Material religioso'),
 @('livros|ebook|e-book|pior ano|novo paradigma','08 Religião e leituras\Livros e desenvolvimento pessoal','Leitura e desenvolvimento pessoal'),
 @('plano.*estrat|estrat.*plano|objetivos.*meta|planejamento|oramento|governanca|fispds|fundo a fundo','09 Trabalho\Planejamento orçamento e projetos','Planejamento e projetos'),
 @('petroleo|narco brasil|programa.de.acao.na.seguranca','09 Trabalho\Planos de operações','Planejamento operacional'),
 @('^sei|sei_|^oficio|^memorando|termo de referencia|relatorio trimestral|relatorio_docente|sintese das altera','09 Trabalho\Processos SEI ofícios e relatórios','Documento administrativo'),
 @('decreto|^lei|portaria|resolucao|boletim|^bg |adt ao bg|^bi dp|edital','09 Trabalho\Legislação editais e boletins','Norma ou publicação administrativa'),
 @('manual.*reda|padronizacao|gestoderisco|ddgv','09 Trabalho\Manuais e procedimentos','Manual de trabalho'),
 @('ciosp|sesed|efetivo|pmrn|comandantes|sinistros|sinesp|dci|pronasci|cadeiras|funcionarios','09 Trabalho\CIOSP SESED e pessoal','Organização e atividade institucional'),
 @('maximus|portifolio|assessoria de comunicacao','09 Trabalho\Consultoria e comunicação','Material profissional'),
 @('camscanner|^scan ','99 Revisar conteúdo\Digitalizações sem assunto no nome','Não é possível inferir o assunto pelo nome'),
 @('^documento|^download|^word|^sem.titulo|^[0-9a-f_-]+( \(\d+\))?\.pdf$|^\d+[.-]|^\d+_|^m\d|^r%|^[a-f0-9]{8}-','99 Revisar conteúdo\Nomes genéricos e códigos','Não é possível inferir o assunto pelo nome')
)
$plan=@(foreach($file in (Get-ChildItem -LiteralPath $root -File -Filter '*.pdf')) {
 $name=Normalize-Name $file.Name
 $category='99 Revisar conteúdo\Assunto a confirmar'; $reason='Nome insuficiente para classificação segura'
 foreach($rule in $rules){if($name -match $rule[0]){$category=$rule[1];$reason=$rule[2];break}}
 [pscustomobject]@{Origem=$file.FullName;Destino=(Join-Path (Join-Path $root $category) $file.Name);Grupo=$category;Criterio=$reason;Estado='Planejado'}
})
$plan | Export-Csv -LiteralPath (Join-Path $PSScriptRoot 'plano-agrupamento-pdfs.csv') -Encoding utf8 -NoTypeInformation
if(-not $Aplicar){$plan | Group-Object Grupo | Select-Object Count,Name | Format-Table -AutoSize; Write-Output "Total: $($plan.Count)"; exit}
foreach($item in $plan){
 try {
  $dest=[IO.Path]::GetFullPath($item.Destino)
  if(-not $dest.StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase) -or -not $item.Origem.StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase)){throw 'Caminho fora de PDFs'}
  $parent=Split-Path $dest
  $check=$parent
  while($check -ne $root){if((Test-Path -LiteralPath $check) -and ((Get-Item -LiteralPath $check).Attributes -band [IO.FileAttributes]::ReparsePoint)){throw 'Destino contém link'};$check=Split-Path $check}
  if(-not(Test-Path -LiteralPath $parent)){New-Item -ItemType Directory -Path $parent -Force | Out-Null}
  if(Test-Path -LiteralPath $dest){throw 'Destino já existe'}
  Move-Item -LiteralPath $item.Origem -Destination $dest
  if(-not(Test-Path -LiteralPath $dest) -or (Test-Path -LiteralPath $item.Origem)){throw 'Falha de verificação'}
  $item.Estado='Movido'
 }catch{$item.Estado='Pendente: '+$_.Exception.Message}
}
$plan | Export-Csv -LiteralPath (Join-Path $PSScriptRoot 'resultado-agrupamento-pdfs.csv') -Encoding utf8 -NoTypeInformation
$plan | Export-Csv -LiteralPath (Join-Path $root 'INDICE - arquivos e criterios.csv') -Encoding utf8 -NoTypeInformation
@'
GUIA DE REVISÃO DOS PDFs

Classificação feita pelo nome do arquivo, sem leitura do conteúdo.
01 a 09: assuntos e finalidades. 99: nomes que exigem abrir o documento.

SUGESTÃO DE DESCARTE nas pastas temáticas:
Possíveis documentos temporários. Confira se a finalidade terminou e se precisa guardá-los. Não significa que estejam vencidos ou sem valor.

SUGESTÃO DE DESCARTE já existente na raiz:
Cópias idênticas identificadas anteriormente por comparação de conteúdo.

Documentos financeiros, fiscais, de identificação, contratos e exames foram agrupados para revisão, sem recomendação automática de descarte.
Nada foi excluído. Nomes com (1), (2), final ou compressed não provam duplicidade ou obsolescência.

O arquivo INDICE - arquivos e criterios.csv relaciona o caminho original, o novo caminho e o critério de cada documento.
'@ | Set-Content -LiteralPath (Join-Path $root 'LEIA-ME - guia de revisão.txt') -Encoding utf8
$plan | Group-Object Estado | Select-Object Count,Name | Format-Table
[pscustomobject]@{Grupos=@($plan.Grupo | Sort-Object -Unique).Count;Sugestoes=@($plan | Where-Object Grupo -like '*Sugestão de descarte*').Count;RevisarConteudo=@($plan | Where-Object Grupo -like '99*').Count;PDFsRestantesNaRaiz=@(Get-ChildItem -LiteralPath $root -File -Filter '*.pdf').Count} | Format-List
