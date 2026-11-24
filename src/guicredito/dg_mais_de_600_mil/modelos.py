"""Modelos de dados da pesquisa DJEN acima de R$ 600.000,00."""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from guicredito.djen.modelos import CadernoInfo, CasoPontuado

CORTE_CENTAVOS = 60_000_000
CORTE_REAIS = Decimal("600000.00")


class StatusValor(StrEnum):
    CONFIRMADO_ACIMA = "confirmado_acima_corte"
    CONFIRMADO_ATE = "confirmado_ate_corte"
    PENDENTE = "pendente"


class MotivoPendencia(StrEnum):
    NAO_CONSULTADO = "nao_consultado"
    CAPA_SEM_VALOR = "capa_sem_valor"
    VALOR_AMBIGUO = "valor_ambiguo"
    CAPA_CNJ_DIVERGENTE = "capa_cnj_divergente"
    EVIDENCIA_INVALIDA = "evidencia_invalida"
    CONSULTA_INTERROMPIDA = "consulta_interrompida"
    NAO_LOCALIZADO = "nao_localizado"
    CONSULTAR_EPROC = "consultar_eproc"
    CNJ_INVALIDO = "cnj_invalido"


ROTULOS_MOTIVO: dict[str, str] = {
    MotivoPendencia.NAO_CONSULTADO: "Ainda não consultado",
    MotivoPendencia.CAPA_SEM_VALOR: "Capa sem valor da causa",
    MotivoPendencia.VALOR_AMBIGUO: "Valor da causa ambíguo ou ilegível",
    MotivoPendencia.CAPA_CNJ_DIVERGENTE: "Capa com CNJ divergente",
    MotivoPendencia.EVIDENCIA_INVALIDA: "Evidência local inválida ou corrompida",
    MotivoPendencia.CONSULTA_INTERROMPIDA: "Consulta interrompida",
    MotivoPendencia.NAO_LOCALIZADO: "Não localizado no e-SAJ",
    MotivoPendencia.CONSULTAR_EPROC: "Tramitação no eproc (conferência manual)",
    MotivoPendencia.CNJ_INVALIDO: "CNJ incompatível com TJSP (8.26)",
}


def rotulo_motivo(motivo: str | None) -> str:
    if not motivo:
        return "Pendente de confirmação"
    return ROTULOS_MOTIVO.get(motivo, motivo)


@dataclass(frozen=True)
class VerificacaoValor:
    """Resultado auditável da verificação do valor da causa de um CNJ."""

    numero_processo: str
    status: StatusValor
    motivo: str | None = None
    detalhe: str = ""
    valor_centavos: int | None = None
    valor_reais: Decimal | None = None
    valor_texto: str | None = None
    fonte: str | None = None
    url_fonte: str | None = None
    consultado_em: str | None = None
    evidencia_arquivo: str | None = None
    evidencia_sha256: str | None = None
    resolvido_localmente: bool = False

    def para_dict(self) -> dict[str, object]:
        return {
            "numero_processo": self.numero_processo,
            "status": str(self.status),
            "motivo": self.motivo,
            "detalhe": self.detalhe,
            "valor_centavos": self.valor_centavos,
            "valor_reais": str(self.valor_reais) if self.valor_reais is not None else None,
            "valor_texto": self.valor_texto,
            "fonte": self.fonte,
            "url_fonte": self.url_fonte,
            "consultado_em": self.consultado_em,
            "evidencia_arquivo": self.evidencia_arquivo,
            "evidencia_sha256": self.evidencia_sha256,
            "resolvido_localmente": self.resolvido_localmente,
        }


@dataclass(frozen=True)
class CasoConfirmado:
    caso_pontuado: CasoPontuado
    verificacao: VerificacaoValor


@dataclass(frozen=True)
class CasoPendente:
    caso_pontuado: CasoPontuado
    verificacao: VerificacaoValor
    mencao_valor_alto: Decimal | None = None


@dataclass(frozen=True)
class CandidatoDiario:
    """Processo elegível com menção > R$ 600 mil no texto do diário."""

    caso_pontuado: CasoPontuado
    verificacao: VerificacaoValor
    mencao_valor_alto: Decimal


@dataclass
class ResumoRodadaFiltrada:
    inicio: date
    fim: date
    tribunal: str
    cadernos: list[CadernoInfo]
    dias_sem_caderno: list[date]
    publicacoes_lidas: int
    publicacoes_cobranca: int
    processos: int
    processos_so_empresa: int
    processos_banco: int
    processos_acordo: int
    processos_recentes: int
    dias_historico: int
    elegiveis: int
    confirmados_acima_corte: int
    confirmados_ate_corte: int
    pendentes: int
    exportados: int
    limite_exibicao: int | None
    consultas_nesta_rodada: int
    reutilizados_locais: int
    somente_capas_locais: bool
    gerado_em: datetime
    interrompido_por: str | None = None
    pendencias_por_motivo: dict[str, int] = field(default_factory=dict)
    so_mencao_diario: bool = False
    candidatos_mencao_diario: int = 0
    candidatos_mencao_pendentes: int = 0
    cache_cadernos_reutilizado: bool = False

    @property
    def cobertura_parcial(self) -> bool:
        return self.pendentes > 0
