"""Find the phrases that add or remove points on a case.

``casos.resumir`` calls ``detectar_sinais`` on the text of one publication.
``texto.frases`` splits that text. Each sentence is normalized, then any
span that matches ``PADROES`` is blanked out. Those spans are repeated
TJSP boilerplate (fee instructions, generic SisbaJud notices, the
Defensoria template). What remains is checked against ``CATALOGO``: one
hit per key, kept as a ``Sinal`` from ``modelos``.

The block on each signal (settlement, real estate, final judgment, wear,
vehicle, discount, alert) is what ``pontuacao`` later sums, up to that
block's cap. ``acordo_homologado`` is worth 0 here: ``casos.montar_casos``
uses it to mark a case as settled (``pipeline`` drops it), and
``casos.marcar_acordos`` turns it into points on the debtor's *other*
cases. ``acordo_descumprido`` undoes that settlement; the warnings that
only say what happens *if* the deal breaks do not match it.
``penhora_levantada`` (an order lifting the seizure, not a request for
it) removes the ``penhora`` and ``imovel_penhorado`` hits of its own
publication, and ``casos`` removes the older ones. The label and
the quoted sentence are what ``planilha`` prints in the signal columns.
"""

import re

from guicredito.djen.modelos import Bloco, Sinal
from guicredito.djen.texto import frases, normalizar

PADROES: list[re.Pattern[str]] = [
    re.compile(r"salvo se (a parte for )?beneficiari.*justica gratuita"),
    re.compile(r"artigo 485.*arquivo provisorio"),
    re.compile(r"para viabilizar a realizacao da\(s\) pesquisa.*"),
    re.compile(r"bloqueio nao incidira sobre valores impenhoraveis"),
    re.compile(r"autorizo, desde ja, o acesso aos sistemas renajud"),
    re.compile(r"ciencia a parte interessada acerca da resposta da ordem pelo sistema sisbajud.*"),
    re.compile(r"acaso nao seja beneficiario da justica gratuita"),
    re.compile(
        r"quando representado pela defensoria publica ou nao tiver procurador"
        r".*indisponibilidade em penhora"
    ),
    re.compile(r"quando representado pela defensoria publica ou nao tiver procurador"),
    re.compile(r"registro geral de indicacao da defensoria"),
    re.compile(r"cumprimento de sentenca relativo a acordo homologado"),
    re.compile(r"\[penhora de imovel\] se houver requerimento de penhora de imovel"),
]

CATALOGO: list[tuple[str, Bloco, int, str, re.Pattern[str]]] = [
    (
        "bloqueio_negativo",
        Bloco.DESGASTE,
        10,
        "bloqueio infrutífero",
        re.compile(
            r"(sisbajud|bacenjud).{0,60}(infrutif|negativ)"
            r"|bloqueio.{0,80}(negativ|infrutif)"
        ),
    ),
    (
        "acordo_frustrado",
        Bloco.DESGASTE,
        10,
        "acordo frustrado",
        re.compile(r"(conciliacao|acordo).{0,40}infrutif|nao houve acordo"),
    ),
    (
        "arquivamento_provisorio",
        Bloco.DESGASTE,
        8,
        "arquivamento provisório",
        re.compile(r"arquiv\w*.{0,15}provisori\w*"),
    ),
    (
        "acordo_descumprido",
        Bloco.DESGASTE,
        0,
        "acordo descumprido",
        re.compile(
            r"(?:noticia|informacao|noticiad\w*|alegad\w*|reconhecendo|em virtude|em razao|por)"
            r"(?: de| do| d[ae] que houve| o)? (?:o )?(?:descumprimento|inadimplemento)"
            r" d[oe]s? (?:termos do )?acordo"
            r"|descumprid[oa] o acordo|acordo (?:judicial )?homologado e descumprido"
            r"|(?:nao cumpriu|descumpriu|deixou de cumprir) o acordo"
            r"|reiterado inadimplemento do acordo"
        ),
    ),
    (
        "acordo_homologado",
        Bloco.ACORDO,
        0,
        "acordo homologado neste processo",
        re.compile(
            r"homologo\w*,?(?: por sentenca,?)? (?:o |os )?(?:presente )?acordo"
            r"|homologad[oa] o acordo|acordo (?:ja )?homologado"
        ),
    ),
    (
        "transito_em_julgado",
        Bloco.TRANSITO,
        15,
        "trânsito em julgado",
        re.compile(
            r"transitou em julgado|(?:acordao|sentenca|decisao) transitad[oa] em julgado"
            r"|certifico(?: que)? o transito em julgado|ocorreu o transito em julgado"
        ),
    ),
    (
        "penhora_levantada",
        Bloco.ALERTA,
        0,
        "⚠ penhora levantada",
        # A lift that names a vehicle, rent, wages and so on says nothing
        # about real estate, so the sentence must not name one of those.
        re.compile(
            r"^(?!.*\b(?:veiculo|motocicleta|renajud|automovel|alugue\w*|salario|faturamento"
            r"|rosto dos autos|cotas sociais|sisbajud)\b).*?(?:"
            r"(?:fica|ficam|dou por|deve ser|devem ser|seja|sejam)"
            r" (?:levantad|desconstituid|cancelad|liberad)\w* (?:a|as) penhoras?\b"
            r"|(?<![a-z])(?:determino|defiro|autorizo|providencie|proceda-se|efetivacao)\b.{0,30}?"
            r"(?:levantamento|desconstituicao|cancelamento|baixa|liberacao) d[ao]s? penhoras?\b"
            r"|(?<![a-z])(?:desconstituo|levanto|cancelo) (?:a|as) penhoras?\b"
            r"|penhoras?\b.{0,40}?(?:ora|ja foi|foi|foram) (?:levantad|desconstituid|cancelad|liberad)"
            r")"
        ),
    ),
    (
        "leilao_negativo",
        Bloco.IMOVEL,
        20,
        "leilão negativo",
        re.compile(
            r"\b(leilao|praca|hasta)\b.{0,80}(negativ|desert)"
            r"|(negativ|desert).{0,40}\b(leilao|praca|hasta)\b"
        ),
    ),
    (
        "imovel_penhorado",
        Bloco.IMOVEL,
        15,
        "imóvel penhorado/avaliado",
        re.compile(r"penhor\w*.{0,25}imovel|avaliacao do imovel|imovel de matricula"),
    ),
    (
        "bem_de_familia",
        Bloco.IMOVEL,
        8,
        "bem de família",
        re.compile(r"bem de familia"),
    ),
    (
        "penhora",
        Bloco.IMOVEL,
        6,
        "penhora",
        re.compile(r"\bpenhora\b"),
    ),
    (
        "veiculo",
        Bloco.VEICULO,
        3,
        "veículo",
        re.compile(r"\brenajud\b|\bveiculo\b"),
    ),
    (
        "superendividamento",
        Bloco.DESCONTO,
        -10,
        "⚠ superendividamento",
        re.compile(r"superendividamento"),
    ),
    (
        "gratuidade_devedor",
        Bloco.DESCONTO,
        -5,
        "⚠ justiça gratuita (devedor)",
        re.compile(
            r"(?<![a-z])(?:defir|deferid|conced)\w*.{0,80}"
            r"(?:executad[oa]|devedor).{0,80}justica gratuita"
            r"|(?:executad[oa]|devedor).{0,80}(?<![a-z])(?:defir|deferid|conced)\w*"
            r".{0,60}justica gratuita"
        ),
    ),
    (
        "defensoria",
        Bloco.DESCONTO,
        -5,
        "⚠ Defensoria Pública",
        re.compile(r"defensoria"),
    ),
    (
        "idoso",
        Bloco.ALERTA,
        0,
        "⚠ idoso(a)",
        re.compile(r"\bidos[oa]\b"),
    ),
    (
        "salario_impenhoravel",
        Bloco.ALERTA,
        0,
        "⚠ salário/aposentadoria impenhorável",
        re.compile(
            r"(salario|aposentadoria|proventos).{0,60}impenhor"
            r"|impenhor.{0,60}(salario|aposentadoria|proventos)"
        ),
    ),
    (
        "sem_bens",
        Bloco.DESCONTO,
        -10,
        "⚠ sem bens localizados",
        re.compile(
            r"nao foram localizados bens|ausencia de bens|execucao frustrada"
            r"|artigos?\s*921|art\.?\s*921"
        ),
    ),
    (
        "prescricao_intercorrente",
        Bloco.DESCONTO,
        -10,
        "⚠ prescrição intercorrente",
        re.compile(r"prescricao intercorrente"),
    ),
    (
        "devedor_nao_localizado",
        Bloco.ALERTA,
        0,
        "⚠ devedor não localizado",
        re.compile(r"devolvida sem cumprimento|nao foi localizado|citacao negativa"),
    ),
]


# Signals a "penhora levantada" cancels, in its own publication and in older ones.
PENHORAS_LEVANTAVEIS = frozenset({"imovel_penhorado", "penhora"})


def eh_texto_padrao(frase_normalizada: str) -> bool:
    return any(padrao.search(frase_normalizada) for padrao in PADROES)


def _sem_trecho_padrao(frase_normalizada: str) -> str:
    texto = frase_normalizada
    for padrao in PADROES:
        texto = padrao.sub(" ", texto)
    return texto


def detectar_sinais(texto: str) -> tuple[Sinal, ...]:
    vistos: set[str] = set()
    achados: list[Sinal] = []
    for frase in frases(texto):
        norm = _sem_trecho_padrao(normalizar(frase))
        if not norm.strip():
            continue
        for chave, bloco, pontos, rotulo, regex in CATALOGO:
            if chave in vistos or not regex.search(norm):
                continue
            vistos.add(chave)
            achados.append(Sinal(chave, bloco, pontos, rotulo, frase[:300]))
    if "penhora_levantada" in vistos:
        achados = [sinal for sinal in achados if sinal.chave not in PENHORAS_LEVANTAVEIS]
    return tuple(achados)
