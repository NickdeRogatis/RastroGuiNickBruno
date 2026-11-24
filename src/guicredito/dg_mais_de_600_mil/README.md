# Pesquisa DJEN acima de R$ 600.000,00 (`--mais-de-600-mil`)

Este módulo implementa o segundo modo do comando `python -m guicredito.djen`: uma pesquisa avulsa de processos elegíveis do TJSP cujo **valor da causa seja estritamente maior que R$ 600.000,00** (entra a partir de **R$ 600.000,01**; **R$ 599.999,99** e **R$ 600.000,00** ficam fora).

Ele roda sobre **todo o universo elegível antes do corte de 300** do modo normal, preservando as mesmas regras de cobrança, exclusões, histórico de acordos, pontuação e desempates. Toda escrita fica isolada sob `saida/DG__mais_de_600_mil/`.

## Preparar o terminal (Mac Studio ou Terminal do PyCharm)

```zsh
cd /Users/nickderogatis/Desktop/RastroGuiNickBruno
export PYTHONPATH="$PWD/src"
```

## Os dois comandos principais

```zsh
# 1) Diário normal (com as opções, corte padrão de 300 e saída já existentes)
.venv/bin/python -m guicredito.djen

# 2) Pesquisa acima de R$ 600 mil (usando o período padrão do diário)
.venv/bin/python -m guicredito.djen --mais-de-600-mil
```

Para ver todas as opções do modo filtrado:

```zsh
.venv/bin/python -m guicredito.djen --mais-de-600-mil --help
```

## Exemplo por período escolhido

```zsh
.venv/bin/python -m guicredito.djen --mais-de-600-mil \
  --inicio 2026-11-12 --fim 2026-11-23
```

Opções úteis:

- `--so-mencao-diario`: restringe as consultas avulsas no e-SAJ aos candidatos que citam valores > R$ 600 mil no texto do diário e adiciona a aba **Candidatos (diário)** na planilha (nunca confirma sem a capa do e-SAJ).
- `--historico N`: lê `N` dias úteis anteriores a `--inicio` apenas para identificar acordos em outros processos (mantém a mesma pontuação do modo normal).
- `--limite N`: limita as linhas exibidas na aba **Casos** **depois** da confirmação financeira (sem `--limite`, exporta todos os confirmados acima de R$ 600.000,00).
- `--max-consultas N`: limita quantas consultas avulsas novas são enviadas ao e-SAJ por rodada (padrão: `10`, para evitar varredura automática do portal).
- `--intervalo SEG`: intervalo entre consultas avulsas ao e-SAJ (padrão: `5.0`, mínimo `3.0`).
- `--sem-cache`: força releitura completa dos cadernos `.zip` (por padrão, a rodada salva `cache_rodada.json.gz` em `saida/DG__mais_de_600_mil/rodadas/` para retomar em segundos).

### Funil pelo texto do DJEN + consulta só nos candidatos

```zsh
.venv/bin/python -m guicredito.djen --mais-de-600-mil \
  --so-mencao-diario --max-consultas 30 --intervalo 5
```

## Como testar usando apenas capas locais (sem novas consultas individuais)

Use `--somente-capas-locais` para validar o filtro apenas com os cadernos já baixados em `dados/cadernos/` e as capas já salvas em `saida/aprofundamento/` e `saida/DG__mais_de_600_mil/capas/`, sem enviar nenhuma consulta individual ao portal e-SAJ:

```zsh
.venv/bin/python -m guicredito.djen --mais-de-600-mil \
  --inicio 2026-11-12 --fim 2026-11-23 \
  --somente-capas-locais
```

## Como retomar a mesma rodada e incorporar novas evidências

Cada capa consultada é gravada imediatamente em `saida/DG__mais_de_600_mil/capas/<cnj>/` junto com seu HTML e `resultado.json`, e cada etapa é registrada em `saida/DG__mais_de_600_mil/rodadas/<SIGLA>_<inicio>_a_<fim>/`.

- **Para retomar**: repita exatamente o mesmo comando com as mesmas datas (`--inicio` e `--fim`). Processos já confirmados (acima ou até o corte) ou com capa já verificada não são consultados de novo, e não há duplicação de linhas.
- **Se houver bloqueio, captcha ou erro de rede**: o comando interrompe imediatamente as novas consultas, salva os resultados já obtidos e atualiza a planilha e a lista de pendências com indicação de **cobertura parcial**.
- **Para incorporar novas evidências locais**: qualquer capa válida adicionada em `saida/aprofundamento/` (somente leitura) ou em `saida/DG__mais_de_600_mil/capas/<cnj>/` (incluindo HTMLs importados via `importar_capa_html`) é verificada por CNJ e SHA-256 e incorporada automaticamente na próxima execução.

## Como abrir a planilha filtrada no Mac

```zsh
open saida/DG__mais_de_600_mil/casos_djen_2026-11-12_a_2026-11-23.xlsx
```

Para mostrar a pasta do filtro no Finder:

```zsh
open saida/DG__mais_de_600_mil
```

As duas planilhas (normal e filtrada) coexistem para as mesmas datas:

| Modo | Arquivo |
|---|---|
| Normal | `saida/casos_djen_AAAA-MM-DD_a_AAAA-MM-DD.xlsx` |
| Filtrado | `saida/DG__mais_de_600_mil/casos_djen_AAAA-MM-DD_a_AAAA-MM-DD.xlsx` |

## Árvore de pastas e isolamento

```text
src/guicredito/
├── djen/                      ← diário normal (apenas expõe --mais-de-600-mil e encaminha)
├── aprofundamento/            ← extração de capa, CNJ e cliente e-SAJ reutilizados
├── pessoas/                   ← pesquisa de pessoas (intocada)
└── dg_mais_de_600_mil/        ← código do filtro e este README.md

tests/
└── dg_mais_de_600_mil/        ← testes do filtro, CLI e isolamento

saida/
├── casos_djen_…xlsx           ← planilha normal (preservada)
├── aprofundamento/            ← somente leitura para o filtro
├── pessoas/                   ← intocada pelo filtro
└── DG__mais_de_600_mil/       ← única área de escrita do modo filtrado
    ├── casos_djen_…xlsx       ← planilha filtrada (Casos, Publicações, Pendentes, Como ler)
    ├── capas/                 ← novas capas consultadas e suas evidências HTML + SHA-256
    ├── cadernos/              ← cadernos que precisarem ser baixados pelo filtro
    └── rodadas/               ← resumo.json, pendentes.csv e eventos.jsonl por período
```

## O que a planilha filtrada contém

- **Casos**: apenas processos confirmados com valor da causa **> R$ 600.000,00**, com as 15 colunas habituais do DJEN mais **Valor da causa (R$)** (numérico), **Fonte do valor** (verificável) e **Data da consulta**.
- **Publicações**: publicações do período vinculadas apenas aos processos exibidos em **Casos**.
- **Pendentes**: CNJ, pontuação, motivo da pendência (ex.: *Ainda não consultado*, *Capa sem valor da causa*, *Valor da causa ambíguo ou ilegível*, *Capa com CNJ divergente*, *Consulta interrompida*) e detalhe.
- **Como ler**: guia de leitura, regras de pontuação, indicação explícita de **Cobertura parcial** enquanto houver pendências e contagens reconciliadas (`Confirmados acima` + `Confirmados até` + `Pendentes` = `Elegíveis`).

## Fontes oficiais verificadas para consulta em lote

Antes de adotar o fluxo com capas locais + consultas avulsas retomáveis, foram verificadas as fontes oficiais gratuitas para o TJSP:

1. **API Pública do DataJud (CNJ)** — [Glossário de Dados](https://datajud-wiki.cnj.jus.br/api-publica/glossario/): oferece consulta em lote para o TJSP (`api_publica_tjsp`), porém **não retorna o campo `valorCausa`** (nem dados das partes) nos índices públicos (Portaria CNJ nº 160/2020).
2. **MNI (Modelo Nacional de Interoperabilidade)**: possui o campo `<valorCausa>`, mas exige credenciamento restrito a órgãos/instituições conveniadas, não sendo aberto ao público geral.
3. **Portal e-SAJ do TJSP** — [Comunicado do TJSP](https://portal.tjsp.jus.br/Noticias/Noticia?codigoNoticia=64795): o Tribunal informa que o e-SAJ é destinado à **consulta avulsa externa** e restringe padrões de automação/RPA em massa.

Por esse motivo, nenhuma fonte pública gratuita em lote pôde ser confirmada para `valor da causa` no TJSP. O módulo prioriza o reaproveitamento verificado de capas locais e limita consultas avulsas por rodada (`--max-consultas`), interrompendo imediatamente diante de bloqueio ou captcha.

## Testes automatizados

```zsh
# Testes específicos do modo filtrado
PYTHONPATH=src .venv/bin/python -m pytest -q tests/dg_mais_de_600_mil

# Suíte completa do projeto
PYTHONPATH=src .venv/bin/python -m pytest -q
```
