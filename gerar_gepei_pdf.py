from pathlib import Path

W,H=1190,842
def E(s): return s.replace('—','-').replace('•','-').replace('\\','\\\\').replace('(','\\(').replace(')','\\)')
def T(x,y,s,n=9): return f'0.1 0.15 0.25 rg BT /F1 {n} Tf {x} {y} Td ({E(s)}) Tj ET\\n'
def B(x,y,w,h,title,rows):
    c=f'0.94 0.97 1 rg {x} {y} {w} {h} re f 0.2 0.3 0.5 RG 1 w {x} {y} {w} {h} re S\\n'
    c+=f'0.1 0.3 0.65 rg {x} {y+h-24} {w} 24 re f\\n'+T(x+7,y+h-17,title,10).replace('0.1 0.15 0.25 rg','1 1 1 rg')
    yy=y+h-40
    for r in rows:
        c+=T(x+7,yy,r,7); yy-=13
    return c
def L(a,b,c,d): return f'0.35 0.42 0.55 RG 1 w {a} {b} m {c} {d} l S\\n'
def p1():
    c='1 1 1 rg 0 0 1190 842 re f\\n'+T(42,805,'GEPEI - Modelo minimo consolidado em portugues',20).replace('0.1 0.15 0.25 rg','0.08 0.16 0.32 rg')+T(42,782,'25 tabelas totais | tipos e vinculos consolidados',9)
    c+=T(42,748,'DOMÍNIO ORGANIZACIONAL',9)
    c+=B(42,610,210,105,'organizacao',['id • nome • sigla • ativo'])+B(290,565,250,150,'unidade_organizacional',['id • nome • sigla • tipo_unidade','organizacao_id'])+B(590,610,210,105,'perfil_usuario',['id • usuario_id • unidade_id'])+B(850,610,260,105,'usuario',['id • nome_usuario • email • ativo','autenticacao simplificada'])
    c+=L(252,665,290,640)+L(540,640,590,665)+L(800,665,850,665)+T(42,530,'PLANEJAMENTO E EXECUÇÃO',9)
    c+=B(42,360,235,145,'plano',['id • nome • tipo_plano','inicio • fim • ativo'])+B(315,335,310,170,'item_plano',['tipo_item: ARTEFATO | ACAO | META | FATOR','codigo • titulo • descricao • item_pai_id','situacao • progresso • prazo • valor_alvo'])+B(665,360,230,145,'plano_acao',['id • criado_em • gestor_id • acao_id'])+B(935,315,175,190,'atividade',['id • titulo • situacao • progresso','executor_id • plano_acao_id','datas • custos • recursos'])
    c+=L(277,432,315,420)+L(625,420,665,432)+L(895,432,935,410)+T(42,285,'INDICADORES, RISCOS E RELATÓRIOS',9)
    c+=B(42,95,235,155,'indicador',['id • codigo • nome • formula','unidade • periodicidade • linha_base'])+B(315,95,235,155,'medicao_indicador',['periodo_referencia • valor_medido','registrado_em • valor_esperado','datas do periodo • evidencia'])+B(590,95,250,155,'vinculo_indicador',['tipo_vinculo: ITEM | META | UNIDADE','indicador_id • item_plano_id'])+B(880,170,230,80,'risco',['id • titulo • probabilidade • impacto • situacao'])+B(880,95,230,55,'evento_risco',['tipo: avaliacao/tratamento/aceite/...'])
    c+=L(277,170,315,170)+L(550,170,590,170)+L(840,190,880,210)+L(995,170,995,150)+T(42,45,'Relacoes completas: GEPEI-minimo-portugues.dbml',8)
    return c
def p2():
    c='1 1 1 rg 0 0 1190 842 re f\\n'+T(42,805,'GEPEI - Consolidacoes e infraestrutura',20)+T(42,782,'Detalhamento das tabelas unificadas e regras de transicao.',9)
    c+=B(55,570,330,150,'registro_atividade',['tipo: BLOQUEIO | EVIDENCIA','atividade_id • titulo • situacao','resolucao • responsaveis • evidencia'])+B(430,570,330,150,'evento_risco',['tipo: AVALIACAO | TRATAMENTO | ACEITE','MATERIALIZACAO | NAO_OCORRENCIA | REMEDIACAO','decisao • datas • evidencia • responsavel'])+B(805,570,330,150,'relatorio',['tipo: SETORIAL | TRIMESTRAL','situacao • resumos • fotografia','ciclo/unidade/validador • ano/trimestre'])+B(55,335,330,130,'ciclo_relatorio',['datas do periodo • situacao','criado/encerrado • plano_id'])+B(430,335,330,130,'registro_auditoria',['entidade • campo • valor anterior/novo','usuario • acao • justificativa'])+B(805,335,330,130,'notificacao',['destinatario • tipo • mensagem','canal • situacao • datas'])
    c+=B(55,155,330,110,'plan_link',['source/target plan items','link_kind • nature • validity'])+B(430,155,330,110,'Django infrastructure',['groups • permissions • admin_log','content_type • migrations • session'])+B(805,155,330,110,'Report consolidation',['report.kind: sector/quarterly/consolidated','snapshot preserves closed period'])
    c+=T(55,260,'MATRIZ DE REDUÇÃO',10)
    rows=[('Originais','Nova tabela','Discriminador'),('4 tabelas estratégicas','plan_item','kind'),('blocker + evidence','activity_record','kind'),('3 relações de indicator','indicator_link','link_kind'),('6 eventos de risk','risk_event','kind'),('2 tabelas de report','report','kind'),('ciclos + unidades','report_cycle + report','cycle/unit'),('integração entre planos','plan_link','link_kind')]
    y=230
    for i,r in enumerate(rows):
        c+=f'0.9 0.94 0.98 rg 55 {y-25} 1080 25 re f 0.55 0.62 0.72 RG 0.5 w 55 {y-25} 1080 25 re S\\n'+T(62,y-16,r[0],7)+T(500,y-16,r[1],7)+T(690,y-16,r[2],7); y-=25
    c+=T(55,35,'Antes da migração: criar constraints condicionais, índices equivalentes e views de compatibilidade.',8)
    return c
def stream(c): return f'<< /Length {len(c.encode("latin1"))} >>\\nstream\\n{c}endstream'
pages=[p1(),p2()]; objs=['<< /Type /Catalog /Pages 2 0 R >>','<< /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 >>']
for i in range(2): objs.append(f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {W} {H}] /Resources << /Font << /F1 5 0 R >> >> /Contents {6+i} 0 R >>')
objs += ['<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',stream(pages[0]),stream(pages[1])]
objs=[o.replace('\\n','\n') for o in objs]
out=bytearray(b'%PDF-1.4\n%\n'); offs=[0]
for n,o in enumerate(objs,1): offs.append(len(out)); out+=f'{n} 0 obj\\n{o}\\nendobj\\n'.replace('\\n','\n').encode('latin1')
x=len(out); out+=f'xref\\n0 {len(objs)+1}\\n0000000000 65535 f \\n'.replace('\\n','\n').encode()
for q in offs[1:]: out+=f'{q:010d} 00000 n \\n'.replace('\\n','\n').encode()
out+=f'trailer\\n<< /Size {len(objs)+1} /Root 1 0 R >>\\nstartxref\\n{x}\\n%%EOF\\n'.replace('\\n','\n').encode()
Path('GEPEI-minimo-portugues-grafico.pdf').write_bytes(out)
