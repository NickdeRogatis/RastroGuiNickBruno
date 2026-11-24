"""Fold many publications of one process into a single case.

``pipeline`` calls ``resumir`` on each collection publication, then
``montar_casos`` on that whole list. ``resumir`` asks ``partes`` for the
creditor and debtor names, ``sinais`` for the phrases worth points, and
``texto.ano_cnj`` plus ``anos_citados`` for how old the debt looks.

``montar_casos`` groups by process number. The newest act supplies the
class, the court, the link and the last publication date. The creditor is
the highest-precedence name (fund, then bank, then company, then person).
``so_empresa`` is true when every debtor is a company. ``pipeline`` drops
those before ``pontuacao`` sees them. ``comarca`` shortens the court name
for the Comarca column that ``planilha`` writes.

``acordo_vigente`` is true when the newest settlement news in the case is
``acordo_homologado`` and no later (or same-day) publication says
``acordo_descumprido``. ``pipeline`` drops those cases: the creditor is
being paid and has no reason to sell. A ``penhora_levantada`` erases the
seizure signals of that publication and of every older one.

``marcar_acordos`` runs after ``montar_casos``. A debtor with a settlement
still in force in one process earns 30 points on each of their *other*
processes that have no settlement of their own. Names match after
``normalizar`` and only with three words or more, so short homonyms do
not match.
"""

import re
from collections.abc import Iterable
from dataclasses import replace

from guicredito.djen.modelos import (
    Bloco,
    Caso,
    Parte,
    Publicacao,
    ResumoPublicacao,
    Sinal,
    TipoCredor,
)
from guicredito.djen.partes import eh_empresa, partes_do_cabecalho, tipo_credor
from guicredito.djen.sinais import PENHORAS_LEVANTAVEIS, detectar_sinais
from guicredito.djen.texto import ano_cnj, formatar_cnj, normalizar

_COMARCA = re.compile(r"comarca de\s+(.+)", re.IGNORECASE)
_MARCADOR = re.compile(
    r"processo principal|autos principais|autos de origem|processo de origem|"
    r"autos(?: de)? n|processo(?: de)? n",
    re.IGNORECASE,
)
_CNJ_TJSP = re.compile(r"\d{7}-\d{2}\.(\d{4})\.8\.26\.\d{4}")
_PALAVRAS_MINIMAS = 3
_PRECEDENCIA = (
    TipoCredor.FUNDO,
    TipoCredor.BANCO,
    TipoCredor.EMPRESA,
    TipoCredor.PESSOA,
)


def comarca(orgao: str) -> str:
    achado = _COMARCA.search(orgao)
    if achado:
        nome = achado.group(1).strip()
        cortes = [i for i in (nome.find(" - "), nome.find(",")) if i >= 0]
        if cortes:
            nome = nome[: min(cortes)].strip()
        return nome
    baixo = orgao.casefold()
    if "foro central" in baixo or "regional" in baixo:
        return "São Paulo"
    return orgao


def anos_citados(texto: str) -> tuple[int, ...]:
    anos: list[int] = []
    vistos: set[int] = set()
    for marca in _MARCADOR.finditer(texto):
        trecho = texto[marca.end() : marca.end() + 50]
        for numero in _CNJ_TJSP.finditer(trecho):
            if numero.start() > 20:
                continue
            ano = int(numero.group(1))
            if ano not in vistos:
                vistos.add(ano)
                anos.append(ano)
    return tuple(anos)


def _sem_repetir(nomes: Iterable[str]) -> list[str]:
    vistos: set[str] = set()
    saida: list[str] = []
    for nome in nomes:
        chave = normalizar(nome)
        if chave in vistos:
            continue
        vistos.add(chave)
        saida.append(nome)
    return saida


def resumir(pub: Publicacao) -> ResumoPublicacao:
    credores_cab, devedores_cab = partes_do_cabecalho(pub.texto)
    credores = _sem_repetir(
        [d.nome for d in pub.destinatarios if d.polo == "A"] + credores_cab
    )
    nomes_devedores = _sem_repetir(
        [d.nome for d in pub.destinatarios if d.polo == "P"] + devedores_cab
    )
    return ResumoPublicacao(
        numero_processo=pub.numero_processo,
        data=pub.data,
        tipo=pub.tipo,
        orgao=pub.orgao,
        classe=pub.classe,
        link=pub.link,
        credores=tuple(credores),
        devedores=tuple(Parte(nome, eh_empresa(nome, pub.texto)) for nome in nomes_devedores),
        sinais=detectar_sinais(pub.texto),
        anos_citados=anos_citados(pub.texto),
    )


def _mais_recente(itens: list[ResumoPublicacao]) -> ResumoPublicacao:
    atual = itens[0]
    for item in itens[1:]:
        if item.data >= atual.data:
            atual = item
    return atual


def _credor(nomes: list[str]) -> tuple[str | None, TipoCredor | None]:
    classificados = [(nome, tipo_credor(nome)) for nome in nomes]
    for tipo in _PRECEDENCIA:
        for nome, tipo_nome in classificados:
            if tipo_nome is tipo:
                return nome, tipo
    return None, None


def _em_ordem(itens: list[ResumoPublicacao]) -> list[ResumoPublicacao]:
    return [item for _, item in sorted(enumerate(itens), key=lambda par: (par[1].data, par[0]))]


def _sinais(itens: list[ResumoPublicacao]) -> tuple[Sinal, ...]:
    por_chave: dict[str, Sinal] = {}
    for item in _em_ordem(itens):
        chaves = {sinal.chave for sinal in item.sinais}
        if "penhora_levantada" in chaves:
            for chave in PENHORAS_LEVANTAVEIS:
                por_chave.pop(chave, None)
        for sinal in item.sinais:
            por_chave[sinal.chave] = sinal
    return tuple(por_chave.values())


def _acordo_vigente(itens: list[ResumoPublicacao]) -> bool:
    vigente = False
    for item in _em_ordem(itens):
        chaves = {sinal.chave for sinal in item.sinais}
        if "acordo_descumprido" in chaves:
            vigente = False
        elif "acordo_homologado" in chaves:
            vigente = True
    return vigente


def _ano_divida(numero: str, itens: list[ResumoPublicacao]) -> int:
    ano_caso = ano_cnj(numero)
    if ano_caso is None:
        return 0
    candidatos = [ano_caso]
    for item in itens:
        for ano in item.anos_citados:
            if 1980 <= ano <= ano_caso:
                candidatos.append(ano)
    return min(candidatos)


def montar_casos(resumos: Iterable[ResumoPublicacao]) -> list[Caso]:
    grupos: dict[str, list[ResumoPublicacao]] = {}
    for resumo in resumos:
        grupos.setdefault(resumo.numero_processo, []).append(resumo)
    casos: list[Caso] = []
    for numero, itens in grupos.items():
        atual = _mais_recente(itens)
        nomes_credores = _sem_repetir(nome for item in itens for nome in item.credores)
        credor, tipo = _credor(nomes_credores)
        devedores: list[Parte] = []
        vistos: set[str] = set()
        for item in itens:
            for parte in item.devedores:
                chave = normalizar(parte.nome)
                if chave in vistos:
                    continue
                vistos.add(chave)
                devedores.append(parte)
        pessoas = [parte.nome for parte in devedores if not parte.empresa]
        empresas = [parte for parte in devedores if parte.empresa]
        casos.append(
            Caso(
                numero_processo=numero,
                classe=atual.classe,
                orgao=atual.orgao,
                comarca=comarca(atual.orgao),
                link=atual.link,
                credor=credor,
                tipo_credor=tipo,
                devedor="; ".join(pessoas) or None,
                avalista=bool(pessoas) and bool(empresas),
                so_empresa=bool(empresas) and not pessoas,
                ano_divida=_ano_divida(numero, itens),
                sinais=_sinais(itens),
                ultima_data=atual.data,
                ultimo_tipo=atual.tipo,
                n_publicacoes=len(itens),
                acordo_vigente=_acordo_vigente(itens),
            )
        )
    return casos


def _nomes_para_cruzar(caso: Caso) -> list[str]:
    if caso.devedor is None:
        return []
    nomes = [normalizar(nome) for nome in caso.devedor.split("; ")]
    return [nome for nome in nomes if len(nome.split()) >= _PALAVRAS_MINIMAS]


def marcar_acordos(casos: list[Caso], referencia: Iterable[Caso]) -> list[Caso]:
    acordos: dict[str, set[str]] = {}
    for caso in referencia:
        if not caso.acordo_vigente:
            continue
        for nome in _nomes_para_cruzar(caso):
            acordos.setdefault(nome, set()).add(caso.numero_processo)
    marcados: list[Caso] = []
    for caso in casos:
        if caso.acordo_vigente:
            marcados.append(caso)
            continue
        outros = {
            numero
            for nome in _nomes_para_cruzar(caso)
            for numero in acordos.get(nome, set())
            if numero != caso.numero_processo
        }
        if not outros:
            marcados.append(caso)
            continue
        sinal = Sinal(
            "acordo_outro_processo",
            Bloco.ACORDO,
            30,
            "acordo em outro processo",
            f"Acordo homologado no processo {formatar_cnj(min(outros))}",
        )
        marcados.append(replace(caso, sinais=caso.sinais + (sinal,)))
    return marcados
