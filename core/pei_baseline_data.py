"""Transcrição visual: DADOS INDICADORES.pdf, páginas impressas 46–50.

Valores da coluna 2024; projeções 2025–2034. None significa traço,
sem previsão naquele ano. Não substitui as metas e fórmulas do Apêndice A.
"""


def row(base, final, unit, values, page, mode='level', note='', strict=False):
    return {'baseline_value': base, 'baseline_year': 2024, 'baseline_date': '2024-12-31',
            'baseline_text': 'Não há' if base is None else base,
            'final_value': final, 'unit': unit, 'mode': mode,
            'projections': {str(2025 + i): value for i, value in enumerate(values)},
            'source': 'DADOS INDICADORES.pdf', 'page': page, 'note': note, 'strict': strict}


PERCENT = ['10', '20', '30', '40', '50', '60', '70', '80', '90', '100']
FROM_2026 = [None, '10', '20', '30', '40', '50', '60', '70', '80', '100']
REFERENCE_PARAMETERS = {
    '01.1': row('31.5', '100', '%', ['38.35','45.2','52.05','58.9','65.75','72.6','79.45','86.3','93.15','100'],46),
    '01.2': row('71.5', '70', '%', ['70']*10,46,'threshold'),
    '02.1': row('504','554','servidores',[None,'514',None,'524',None,'534',None,'544',None,'554'],46,note='O quadro apresenta o total de servidores; a meta original descreve crescimento percentual.'),
    '02.2': row('0','10','% de redução',[None,'1','2','3','4','5','6','7','8','10'],46,note='A projeção expressa redução positiva, não o tempo absoluto do processo.'),
    '03.1': row('0','100','%',PERCENT,46),
    '03.2': row('0','27','iniciativas',[None]+['3']*9,46,'annual'),
    '03.3': row('0','70','%',[None]+['70']*9,47,'threshold',strict=True),
    '03.4': row('0','70','%',[None]+['70']*9,47,'threshold'),
    '04.1': row('0','100','%',PERCENT,47),
    '05.1': row('11','50','%',[None,'20',None,'25',None,'30',None,'40',None,'50'],47,note='Mantidos os valores da tabela, apesar da descrição simplificada do incremento bienal.'),
    '05.2': row('0','100','%',[None,'20',None,'40',None,'60',None,'80',None,'100'],47),
    '05.3': row('0','90','ações',[None]+['10']*9,47,'annual',note='O quadro apresenta ações por ano, enquanto a ficha original usa percentual de ações realizadas.'),
    '05.4': row('0','100','%',PERCENT,47),
    '06.1': row('45','73.30','R$ milhões',['47.25','49.61','52.09','54.69','57.43','60.30','63.31','66.48','69.80','73.30'],48,note='O quadro usa montantes em milhões; a fórmula original expressa variação percentual.'),
    '06.2': row('0','10','%',['1','2','3','4','5','6','7','8','9','10'],48),
    '07.1': row('0','10','%',['1','2','3','4','5','6','7','8','9','10'],48),
    '07.2': row('0','40','ações',['4']*10,48,'annual',note='O quadro usa ações anuais; a ficha original descreve percentual de ações.'),
    '07.3': row(None,'100','%',PERCENT,48,note='Linha de base descrita como “Não há”; não foi convertida em zero observado.'),
    '08.1': row('0','100','%',[None,'20','30','40','50','60','70','80','90','100'],48),
    '08.2': row('0','100','%',FROM_2026,48),
    '09.1': row('0','100','%',FROM_2026,48),
    '09.2': row('0','15','soluções',['1']*5+['2']*5,49,'annual',note='O quadro usa soluções entregues no ano; a ficha original descreve índice percentual.'),
    '10.1': row('0','100','processos',['10']*10,49,'annual'),
    '10.2': row('0','10','publicações',['1']*10,49,'annual'),
    '10.3': row('0','-10','% de variação',[None,'-1','-2','-3','-4','-5','-6','-7','-8','-10'],49,note='Redução representada por variação negativa; preservada a meta textual original.'),
    '11.1': row('0','5','parcerias',[None,'1',None,'1',None,'1',None,'1',None,'1'],49,'annual'),
    '11.2': row('0','5','projetos',[None,'1',None,'1',None,'1',None,'1',None,'1'],49,'annual'),
    '12.1': row('0','10','operações',['1']*10,49,'annual'),
    '12.2': row('26.30','20','por 100 mil habitantes',['25.67','25.04','24.41','23.78','23.15','22.52','21.89','21.26','20.63','20'],49),
    '12.3': row('3.80','3','taxa',['3.72','3.64','3.56','3.48','3.4','3.32','3.24','3.16','3.08','3.0'],50,note='A descrição exige abaixo de 3, enquanto a projeção final é 3; preservados os dois registros.',strict=True),
    '12.4': row('508.882','559.77','kg',['513.97','519.058','524.146','529.234','534.322','539.41','544.498','549.586','554.674','559.76'],50,note='A coluna de meta final informa 559,77 kg; a projeção de 2034 informa 559,76 kg. Não foi corrigida a divergência do documento.'),
    '12.5': row('0','-50','% de variação',['-5','-10','-15','-20','-25','-30','-35','-40','-45','-50'],50),
    '13.1': row('0','100','%',PERCENT,50),
    '13.2': row('0','10','ações',['1']*10,50,'annual'),
    '13.3': row('0','70','%',['70']*10,50,'threshold'),
    '13.4': row('0','100','%',PERCENT,50),
    '13.5': row('0','100','% de execução da publicação',PERCENT,50,note='A meta original prevê 10 edições; este quadro projeta 100% de execução. A meta de 10 edições foi preservada.'),
}
