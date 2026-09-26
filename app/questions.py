"""Banco de perguntas baseado no modelo RIASEC (Holland), adaptado para estudantes.

Fase 1: 12 perguntas gerais (2 por dimensão) -> descobre as 3 dimensões mais fortes.
Fase 2: 4 perguntas aprofundadas para cada uma das 3 dimensões mais fortes (12 no total),
        cada uma ligada a uma área profissional, para refinar a sugestão de cursos.
Abertas: 2 perguntas livres, interpretadas pelo LLM no resultado.
"""

DIMENSIONS = {
    "R": {
        "nome": "Realista",
        "descricao": "prático(a), gosta de colocar a mão na massa, lidar com ferramentas, máquinas, natureza e atividades físicas",
    },
    "I": {
        "nome": "Investigativo",
        "descricao": "curioso(a), analítico(a), gosta de entender como as coisas funcionam, pesquisar e resolver problemas",
    },
    "A": {
        "nome": "Artístico",
        "descricao": "criativo(a), expressivo(a), gosta de criar, imaginar e comunicar ideias de forma original",
    },
    "S": {
        "nome": "Social",
        "descricao": "empático(a), gosta de ajudar, ensinar, cuidar e trabalhar com pessoas",
    },
    "E": {
        "nome": "Empreendedor",
        "descricao": "comunicativo(a), gosta de liderar, convencer, negociar e tomar decisões",
    },
    "C": {
        "nome": "Convencional",
        "descricao": "organizado(a), detalhista, gosta de planejamento, números, dados e processos claros",
    },
}

# Áreas profissionais: afinidade com as dimensões + cursos sugeridos
AREAS = {
    "tecnologia": {
        "dia_a_dia": "Resolver problemas com código e dados: criar sistemas, apps e sites, testar, corrigir erros e trabalhar em equipe com gente de outras áreas.",
        "onde_trabalha": ["Empresas de software e startups", "Bancos e fintechs", "Setor de TI de indústrias, hospitais e governo", "Trabalho remoto para empresas de fora", "Negócio próprio (freelancer)"],
        "dicas": ["Comece a programar de graça (Python é uma ótima porta de entrada)", "Capriche em matemática e lógica", "Treine inglês: a maior parte do material é em inglês"],
        "motivo": "você tem raciocínio lógico, curte tecnologia e gosta de resolver problemas de forma organizada",
        "nome": "Tecnologia e Computação",
        "dims": {"I": 0.45, "C": 0.35, "R": 0.2},
        "cursos": ["Ciência da Computação", "Análise e Desenvolvimento de Sistemas", "Engenharia de Software", "Sistemas de Informação", "Ciência de Dados e IA"],
    },
    "engenharia": {
        "dia_a_dia": "Planejar, calcular e acompanhar projetos: obras, máquinas, sistemas elétricos ou processos de produção, entre escritório e campo.",
        "onde_trabalha": ["Construtoras e obras", "Indústrias e usinas", "Empresas de energia", "Consultorias e projetos", "Órgãos públicos"],
        "dicas": ["Foque em matemática e física", "Monte coisas: kits de robótica, Arduino, consertos em casa", "Visite uma obra ou indústria e converse com um engenheiro"],
        "motivo": "você gosta de entender como as coisas funcionam, de colocar a mão na massa e de resolver problemas práticos",
        "nome": "Engenharias",
        "dims": {"R": 0.5, "I": 0.4, "C": 0.1},
        "cursos": ["Engenharia Civil", "Engenharia Mecânica", "Engenharia Elétrica", "Engenharia de Produção", "Engenharia Mecatrônica"],
    },
    "saude": {
        "dia_a_dia": "Cuidar de pessoas: atender, examinar, orientar e acompanhar tratamentos, sempre estudando e trabalhando em equipe.",
        "onde_trabalha": ["Hospitais e clínicas", "Unidades básicas de saúde (SUS)", "Consultório próprio", "Academias e clubes", "Pesquisa e laboratórios"],
        "dicas": ["Capriche em biologia e química", "Pergunte a profissionais da saúde como é a rotina", "Faça trabalho voluntário para ver se gosta de cuidar"],
        "motivo": "você se interessa pelo corpo humano e pelas ciências e tem vontade de cuidar das pessoas",
        "nome": "Saúde e Bem-estar",
        "dims": {"S": 0.5, "I": 0.4, "R": 0.1},
        "cursos": ["Medicina", "Enfermagem", "Fisioterapia", "Odontologia", "Nutrição", "Educação Física", "Farmácia"],
    },
    "bio_agro": {
        "dia_a_dia": "Trabalhar com a natureza: campo, animais, plantas e meio ambiente, com muita prática e pesquisa.",
        "onde_trabalha": ["Fazendas e agronegócio", "Cooperativas", "Clínicas veterinárias", "Empresas de meio ambiente", "Pesquisa (universidades, Embrapa)"],
        "dicas": ["Biologia e química são a base", "Visite propriedades rurais e fale com quem trabalha nelas", "Acompanhe temas de sustentabilidade"],
        "motivo": "você se conecta com a natureza, os animais e o campo e tem curiosidade científica",
        "nome": "Ciências Biológicas, Agrárias e Meio Ambiente",
        "dims": {"R": 0.5, "I": 0.5},
        "cursos": ["Agronomia", "Medicina Veterinária", "Ciências Biológicas", "Zootecnia", "Engenharia Ambiental"],
    },
    "exatas": {
        "dia_a_dia": "Investigar, calcular e modelar: resolver problemas difíceis com matemática, dados e experimentos.",
        "onde_trabalha": ["Pesquisa e universidades", "Bancos e mercado financeiro", "Empresas de tecnologia e dados", "Indústria", "Ensino"],
        "dicas": ["Participe de olimpíadas (OBMEP, OBF, OBQ)", "Estude além do que cai na prova", "Aprenda um pouco de programação"],
        "motivo": "você tem facilidade com números e lógica e gosta de ir a fundo para entender as coisas",
        "nome": "Ciências Exatas",
        "dims": {"I": 0.6, "C": 0.4},
        "cursos": ["Matemática", "Física", "Estatística", "Química"],
    },
    "artes_design": {
        "dia_a_dia": "Criar: transformar ideias em algo visual ou sensorial, testar versões, receber opiniões e refinar o trabalho.",
        "onde_trabalha": ["Estúdios e agências", "Escritórios de arquitetura", "Empresas de tecnologia (design de apps)", "Indústria da moda", "Trabalho autônomo"],
        "dicas": ["Monte um portfólio desde já (Instagram, Behance)", "Pratique desenho e ferramentas gratuitas (Canva, Figma)", "Observe e copie referências para aprender"],
        "motivo": "você é criativo(a), tem olhar estético e gosta de transformar ideias em algo visual",
        "nome": "Artes, Design e Arquitetura",
        "dims": {"A": 0.8, "R": 0.2},
        "cursos": ["Design Gráfico", "Arquitetura e Urbanismo", "Design de Interiores", "Música", "Moda", "Artes Visuais"],
    },
    "comunicacao": {
        "dia_a_dia": "Contar histórias e informar: produzir textos, vídeos, campanhas e conteúdos para diferentes públicos.",
        "onde_trabalha": ["Agências de publicidade", "Veículos de imprensa", "Produtoras de vídeo", "Marketing de empresas", "Criador de conteúdo independente"],
        "dicas": ["Escreva todo dia (redação ajuda muito)", "Crie conteúdo sobre algo que você gosta", "Leia notícias de fontes variadas"],
        "motivo": "você se expressa bem, gosta de criar conteúdo e de prender a atenção das pessoas",
        "nome": "Comunicação e Mídias",
        "dims": {"A": 0.5, "E": 0.3, "S": 0.2},
        "cursos": ["Publicidade e Propaganda", "Jornalismo", "Cinema e Audiovisual", "Marketing Digital", "Letras"],
    },
    "educacao_humanas": {
        "dia_a_dia": "Trabalhar com pessoas: ouvir, ensinar, orientar e entender comportamentos e contextos sociais.",
        "onde_trabalha": ["Escolas e universidades", "Clínicas e consultórios", "ONGs e projetos sociais", "RH de empresas", "Órgãos públicos"],
        "dicas": ["Leia bastante (redação e interpretação são essenciais)", "Faça monitoria ou ajude colegas a estudar", "Participe de projetos sociais"],
        "motivo": "você é empático(a), tem paciência para ouvir e ensinar e se interessa pelas pessoas",
        "nome": "Educação e Ciências Humanas",
        "dims": {"S": 0.7, "A": 0.3},
        "cursos": ["Psicologia", "Pedagogia", "História", "Serviço Social", "Licenciaturas"],
    },
    "direito_publico": {
        "dia_a_dia": "Analisar situações, argumentar e defender direitos: ler muito, escrever bem e negociar soluções.",
        "onde_trabalha": ["Escritórios de advocacia", "Tribunais e Ministério Público", "Empresas (setor jurídico)", "Órgãos públicos (concursos)", "Organizações internacionais"],
        "dicas": ["Treine redação e argumentação", "Participe de debates e simulações da ONU", "Acompanhe notícias de política e sociedade"],
        "motivo": "você gosta de argumentar, defende o que é justo e quer ajudar a resolver problemas da sociedade",
        "nome": "Direito e Gestão Pública",
        "dims": {"E": 0.5, "S": 0.3, "C": 0.2},
        "cursos": ["Direito", "Relações Internacionais", "Ciência Política", "Gestão Pública"],
    },
    "negocios": {
        "dia_a_dia": "Fazer as coisas acontecerem: planejar, liderar pessoas, vender ideias e acompanhar resultados.",
        "onde_trabalha": ["Empresas de todos os setores", "Comércio e varejo", "Startups", "Negócio próprio", "Consultorias"],
        "dicas": ["Venda algo (mesmo pequeno) para aprender na prática", "Aprenda noções de finanças pessoais", "Participe de grêmio ou organize eventos"],
        "motivo": "você tem espírito de liderança, gosta de negociar e de fazer as coisas acontecerem",
        "nome": "Negócios e Empreendedorismo",
        "dims": {"E": 0.7, "C": 0.3},
        "cursos": ["Administração", "Gestão Comercial", "Marketing", "Comércio Exterior", "Economia"],
    },
    "financas_gestao": {
        "dia_a_dia": "Organizar e analisar: controlar números, planejar orçamentos, cuidar de processos e apoiar decisões.",
        "onde_trabalha": ["Escritórios de contabilidade", "Bancos", "Departamentos financeiros e de RH", "Empresas de logística", "Órgãos públicos"],
        "dicas": ["Domine planilhas (Excel ou Google Planilhas)", "Capriche em matemática", "Organize as finanças de um projeto ou da sua casa"],
        "motivo": "você é organizado(a), gosta de números e de planejar com cuidado",
        "nome": "Finanças, Contabilidade e Logística",
        "dims": {"C": 0.7, "E": 0.3},
        "cursos": ["Ciências Contábeis", "Gestão Financeira", "Logística", "Gestão de Recursos Humanos"],
    },
    "tecnico_pratico": {
        "dia_a_dia": "Colocar a mão na massa: instalar, operar, manter e melhorar máquinas e sistemas, com foco em segurança e precisão.",
        "onde_trabalha": ["Indústrias e usinas", "Empresas de manutenção", "Construção civil", "Empresas de energia", "Serviço autônomo"],
        "dicas": ["Procure cursos técnicos (Etec, Senai, IF)", "Aprenda com quem já trabalha na área", "Matemática e física ajudam muito"],
        "motivo": "você é prático(a), detalhista e gosta de trabalhar com máquinas e equipamentos",
        "nome": "Cursos Técnicos e Indústria",
        "dims": {"R": 0.7, "C": 0.3},
        "cursos": ["Técnico em Mecatrônica", "Técnico em Eletrotécnica", "Automação Industrial", "Técnico em Manutenção", "Técnico em Segurança do Trabalho"],
    },
}

SCALE = [
    {"value": 1, "label": "Nada a ver comigo"},
    {"value": 2, "label": "Pouco"},
    {"value": 3, "label": "Mais ou menos"},
    {"value": 4, "label": "Bastante"},
    {"value": 5, "label": "Tudo a ver comigo"},
]

PHASE1 = [
    {"id": "p1_r1", "dim": "R", "texto": "Gosto de montar, consertar ou mexer com máquinas, ferramentas ou equipamentos."},
    {"id": "p1_i1", "dim": "I", "texto": "Tenho curiosidade de entender como as coisas funcionam por dentro (corpo humano, natureza, tecnologia)."},
    {"id": "p1_a1", "dim": "A", "texto": "Gosto de criar coisas: desenhar, escrever, compor, editar vídeos ou fotos."},
    {"id": "p1_s1", "dim": "S", "texto": "Gosto de ajudar colegas a entender a matéria ou a resolver problemas."},
    {"id": "p1_e1", "dim": "E", "texto": "Gosto de liderar grupos, convencer pessoas e tomar decisões."},
    {"id": "p1_c1", "dim": "C", "texto": "Gosto de organizar coisas: listas, agendas, arquivos, planilhas."},
    {"id": "p1_r2", "dim": "R", "texto": "Prefiro atividades práticas, com as mãos ou ao ar livre, a ficar só lendo."},
    {"id": "p1_i2", "dim": "I", "texto": "Gosto de resolver problemas de lógica, matemática ou enigmas."},
    {"id": "p1_a2", "dim": "A", "texto": "Me sinto bem quando posso expressar minhas ideias de um jeito original."},
    {"id": "p1_s2", "dim": "S", "texto": "Me imagino trabalhando para cuidar da saúde, da educação ou do bem-estar das pessoas."},
    {"id": "p1_e2", "dim": "E", "texto": "Já pensei em ter meu próprio negócio ou em vender alguma coisa."},
    {"id": "p1_c2", "dim": "C", "texto": "Fico confortável seguindo regras e processos claros, com atenção aos detalhes."},
]

PHASE2 = {
    "R": [
        {"id": "p2_r1", "area": "tecnico_pratico", "texto": "Gostaria de trabalhar em oficinas, fábricas, obras ou com manutenção de equipamentos."},
        {"id": "p2_r2", "area": "engenharia", "texto": "Tenho interesse em entender como funcionam motores, circuitos elétricos ou construções."},
        {"id": "p2_r3", "area": "bio_agro", "texto": "Gosto de lidar com animais, plantas ou atividades do campo."},
        {"id": "p2_r4", "area": "saude", "texto": "Pratico esportes ou atividades físicas com frequência e gosto disso."},
    ],
    "I": [
        {"id": "p2_i1", "area": "saude", "texto": "Me interesso por biologia, química ou pelo funcionamento do corpo humano."},
        {"id": "p2_i2", "area": "tecnologia", "texto": "Gosto de computadores e tenho curiosidade (ou já tentei) programar."},
        {"id": "p2_i3", "area": "exatas", "texto": "Matemática e física são matérias que eu curto ou em que tenho facilidade."},
        {"id": "p2_i4", "area": "bio_agro", "texto": "Me interesso por natureza, meio ambiente e sustentabilidade."},
    ],
    "A": [
        {"id": "p2_a1", "area": "artes_design", "texto": "Gosto de desenhar, criar layouts, decorar ambientes ou pensar em moda."},
        {"id": "p2_a2", "area": "comunicacao", "texto": "Gosto de escrever, criar conteúdo para redes sociais ou gravar e editar vídeos."},
        {"id": "p2_a3", "area": "artes_design", "texto": "Música, teatro, dança ou cinema fazem parte da minha rotina."},
        {"id": "p2_a4", "area": "comunicacao", "texto": "Gosto de contar histórias e prender a atenção das pessoas."},
    ],
    "S": [
        {"id": "p2_s1", "area": "educacao_humanas", "texto": "Tenho paciência para explicar e ensinar as pessoas."},
        {"id": "p2_s2", "area": "saude", "texto": "Me vejo cuidando de pessoas doentes ou que precisam de apoio."},
        {"id": "p2_s3", "area": "educacao_humanas", "texto": "Me interesso pelo comportamento humano, pelos sentimentos e pelas relações."},
        {"id": "p2_s4", "area": "direito_publico", "texto": "Me incomodo com injustiças e gostaria de ajudar a resolver problemas da sociedade."},
    ],
    "E": [
        {"id": "p2_e1", "area": "negocios", "texto": "Gosto de negociar, vender ou convencer os outros de uma ideia."},
        {"id": "p2_e2", "area": "negocios", "texto": "Me imagino gerenciando uma equipe ou uma empresa."},
        {"id": "p2_e3", "area": "direito_publico", "texto": "Gosto de debater, argumentar e defender meu ponto de vista."},
        {"id": "p2_e4", "area": "financas_gestao", "texto": "Gosto de acompanhar assuntos de economia, dinheiro ou investimentos."},
    ],
    "C": [
        {"id": "p2_c1", "area": "financas_gestao", "texto": "Gosto de trabalhar com números, cálculos e controle de gastos."},
        {"id": "p2_c2", "area": "financas_gestao", "texto": "Sou organizado(a) e gosto de planejar as coisas com antecedência."},
        {"id": "p2_c3", "area": "tecnologia", "texto": "Gostaria de trabalhar com dados, relatórios ou sistemas de computador."},
        {"id": "p2_c4", "area": "tecnico_pratico", "texto": "Presto atenção em detalhes que outras pessoas não percebem."},
    ],
}

MIN_ABERTA = 15  # caracteres mínimos em cada resposta aberta (a IA precisa de algo para ler)

OPEN_QUESTIONS = [
    {"id": "ab_livre", "texto": "O que você mais gosta de fazer no seu tempo livre?", "placeholder": "Ex.: jogar, desenhar, ajudar em casa, treinar, mexer no celular...", "min": MIN_ABERTA},
    {"id": "ab_sonho", "texto": "Já pensou em alguma profissão ou curso? Qual e por quê?", "placeholder": "Se ainda não sabe, conte o que te chama atenção ou o que você não gostaria de fazer.", "min": MIN_ABERTA},
]

PHASE1_IDS = {q["id"] for q in PHASE1}
QUESTION_INDEX = {q["id"]: {**q} for q in PHASE1}
for _dim, _qs in PHASE2.items():
    for _q in _qs:
        QUESTION_INDEX[_q["id"]] = {**_q, "dim": _dim}
OPEN_IDS = {q["id"] for q in OPEN_QUESTIONS}
