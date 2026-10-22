"""Responsabilidades compartilhadas: OBJETIVOS E AÇÕES.pdf, Apêndice B, pp. 51–60.

O documento não distingue um coordenador principal entre os setores listados.
O responsável principal existente é preservado quando pertence ao grupo.
Na p. 55, FUNCEP identifica pelo nome o Fundo Estadual de Segurança Pública,
cadastrado no sistema como FUNSEP. Na p. 53, Setor de Engenharia é ENG.
"""
OBJECTIVE_RESPONSIBILITIES = {
    "01": ("SRH",),
    "02": ("GS", "SRH"),
    "03": ("GS", "SRH"),
    "04": ("GS", "ENG"),
    "05": ("CIOSP", "CTINF"),
    "06": ("SEAQ", "FUNSEP", "SAF", "SPC"),
    "07": ("GS", "SPC"),
    "08": ("GS", "COPIN"),
    "09": ("GS", "COPIN", "CIOSP", "CTINF"),
    "10": ("GSA", "COPIN"),
    "11": ("GS", "SRH", "CTINF", "CIOSP", "COPIN"),
    "12": ("SESED",),
    "13": ("CPCID", "CODIMM", "COINE"),
}
SOURCE_PAGES = {"01": "51", "02": "51–52", "03": "52", "04": "52–53", "05": "53–54", "06": "54–55", "07": "55", "08": "56", "09": "56–57", "10": "57–58", "11": "58", "12": "58–59", "13": "59–60"}
ACTION_COUNTS = {"01": 3, "02": 2, "03": 2, "04": 2, "05": 7, "06": 2, "07": 2, "08": 4, "09": 3, "10": 3, "11": 1, "12": 1, "13": 7}
