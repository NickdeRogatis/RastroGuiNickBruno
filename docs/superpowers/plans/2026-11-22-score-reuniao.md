# Score novo da reunião de 13/11 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refazer a pontuação do achador de casos DJEN na ordem da reunião (acordo em outro processo, imóvel, trânsito em julgado), tirar bancos e casos com menos de 1 ano, e trocar vulnerabilidade por descontos/alertas.

**Architecture:** `sinais.py` ganha sinais novos e muda blocos/pesos. `casos.py` ganha `marcar_acordos`, uma passada que cruza devedores entre processos. `pontuacao.py` passa a somar os blocos novos. `pipeline.py` filtra banco e casos recentes e aceita `--historico N`. `planilha.py` reflete as colunas e a aba Como ler novas.

**Tech Stack:** Python ≥3.12, openpyxl, pytest. Sem dependências novas.

**Spec:** `docs/superpowers/specs/2026-11-22-score-reuniao-design.md` (substitui a seção 9 de `2026-11-08-djen-casos-design.md`).

## Global Constraints

- TDD: teste antes da implementação. Testes com nomes fictícios (JOÃO EXEMPLO, BANCO EXEMPLO S.A., EMPRESA EXEMPLO LTDA), sem rede.
- Regex de sinal sempre contra `texto.normalizar` (sem acento, minúsculo). Frases de `PADROES` (texto-padrão TJSP) nunca pontuam.
- Commits convencionais, verbo no presente, na branch `feature/djen-casos`. Rodapé: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- `dados/` e `saida/` nunca vão para o git.
- Ambiente: o `.venv` não existe neste checkout. Antes da Task 1: `python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'`. Rodar testes com `.venv/bin/python -m pytest`.

## Review Focus

1. Mesmo devedor escrito com acento/caixa/espaço diferentes em dois processos ("JOSÉ CARLOS DA SILVA" × "Jose Carlos da  Silva") deve casar. → teste na Task 2.
2. Caso com dois devedores (`devedor = "A; B"`): o acordo de qualquer um deles conta. → teste na Task 2.
3. Processo que aparece tanto no histórico quanto no período: o acordo do próprio processo não vira "outro processo". → teste na Task 2.
4. Dia do histórico sem caderno (404): imprime `sem caderno em dd/mm` e segue; não entra em `dias_sem_caderno` do período. → teste na Task 4.
5. `ano_divida == 0` (número sem ano legível) não pode ser tratado como recente nem quebrar. → teste na Task 3.
6. "Após o trânsito em julgado, arquivem-se" (futuro, ordem genérica) não pontua; "transitou em julgado" pontua. → teste na Task 1.

---

### Task 1: Blocos e sinais novos

**Files:**
- Modify: `src/guicredito/djen/modelos.py` (`Bloco`)
- Modify: `src/guicredito/djen/sinais.py` (`CATALOGO`, docstring)
- Modify: `src/guicredito/djen/partes.py` (nova `eh_cumprimento`)
- Test: `tests/djen/test_sinais.py`, `tests/djen/test_partes.py`

**Interfaces:**
- Produces: `Bloco` = `ACORDO, IMOVEL, TRANSITO, DESGASTE, VEICULO, DESCONTO, ALERTA` (valores `"acordo"`, `"imovel"`, `"transito"`, `"desgaste"`, `"veiculo"`, `"desconto"`, `"alerta"`). `PATRIMONIO` e `VULNERABILIDADE` deixam de existir.
- Produces: chaves de sinal `acordo_homologado` (ACORDO, 0) e `transito_em_julgado` (TRANSITO, 15).
- Produces: `partes.eh_cumprimento(nome_classe: str) -> bool` — usa o `_CUMPRIMENTO` já existente sobre `normalizar(nome_classe)`.

Tabela final do `CATALOGO` (chave, bloco, pontos, rótulo):

| chave | bloco | pts | rótulo |
|---|---|---|---|
| bloqueio_negativo | DESGASTE | 10 | bloqueio infrutífero |
| acordo_frustrado | DESGASTE | 10 | acordo frustrado |
| arquivamento_provisorio | DESGASTE | 8 | arquivamento provisório |
| acordo_homologado | ACORDO | 0 | acordo homologado neste processo |
| transito_em_julgado | TRANSITO | 15 | trânsito em julgado |
| leilao_negativo | IMOVEL | 20 | leilão negativo |
| imovel_penhorado | IMOVEL | 15 | imóvel penhorado/avaliado |
| bem_de_familia | IMOVEL | 8 | bem de família |
| penhora | IMOVEL | 6 | penhora |
| veiculo | VEICULO | 3 | veículo |
| superendividamento | DESCONTO | −10 | ⚠ superendividamento |
| gratuidade_devedor | DESCONTO | −5 | ⚠ justiça gratuita (devedor) |
| defensoria | DESCONTO | −5 | ⚠ Defensoria Pública |
| idoso | ALERTA | 0 | ⚠ idoso(a) |
| salario_impenhoravel | ALERTA | 0 | ⚠ salário/aposentadoria impenhorável |
| sem_bens | DESCONTO | −10 | ⚠ sem bens localizados |
| prescricao_intercorrente | DESCONTO | −10 | ⚠ prescrição intercorrente |
| devedor_nao_localizado | ALERTA | 0 | ⚠ devedor não localizado |

Regexes existentes ficam iguais. Novas:
- `acordo_homologado`: `homologo\w*.{0,40}acordo|acordo.{0,40}homologad|acordo celebrado entre as partes`
- `transito_em_julgado`: `transitou em julgado|transitad[oa] em julgado|certific\w*.{0,40}transito em julgado|ocorreu o transito em julgado` (só passado; "após o trânsito em julgado" não casa).

`acordo_homologado` deve vir **antes** de `acordo_frustrado` não é necessário (chaves independentes), mas "não houve acordo" não pode disparar `acordo_homologado`.

- [ ] **Step 1: Ajustar testes existentes em `test_sinais.py`** que citam `Bloco.PATRIMONIO`/`VULNERABILIDADE` ou os pontos antigos para a tabela acima.
- [ ] **Step 2: Escrever testes novos**

```python
def test_acordo_homologado_nao_pontua_no_proprio_caso():
    (s,) = [x for x in detectar_sinais("Homologo o acordo celebrado entre as partes.") if x.chave == "acordo_homologado"]
    assert (s.bloco, s.pontos) == (Bloco.ACORDO, 0)

def test_nao_houve_acordo_nao_e_homologado():
    assert "acordo_homologado" not in {x.chave for x in detectar_sinais("Não houve acordo.")}

def test_transito_passado_pontua():
    (s,) = [x for x in detectar_sinais("A sentença transitou em julgado em 2019.") if x.chave == "transito_em_julgado"]
    assert (s.bloco, s.pontos) == (Bloco.TRANSITO, 15)

def test_transito_futuro_nao_pontua():
    assert "transito_em_julgado" not in {x.chave for x in detectar_sinais("Após o trânsito em julgado, arquivem-se.")}

def test_vulnerabilidade_virou_desconto_e_alerta():
    achados = {x.chave: (x.bloco, x.pontos) for x in detectar_sinais(
        "Pedido de superendividamento. Assistido pela Defensoria. Executado idoso.")}
    assert achados["superendividamento"] == (Bloco.DESCONTO, -10)
    assert achados["defensoria"] == (Bloco.DESCONTO, -5)
    assert achados["idoso"] == (Bloco.ALERTA, 0)

def test_veiculo_vale_3():
    (s,) = [x for x in detectar_sinais("Restrição via RENAJUD do veículo.") if x.chave == "veiculo"]
    assert (s.bloco, s.pontos) == (Bloco.VEICULO, 3)
```

Em `test_partes.py`: `eh_cumprimento("CUMPRIMENTO DE SENTENçA")` é True; `eh_cumprimento("EXECUÇÃO DE TÍTULO EXTRAJUDICIAL")` é False.

- [ ] **Step 3: Rodar** `.venv/bin/python -m pytest tests/djen/test_sinais.py tests/djen/test_partes.py -v` → FAIL (blocos/chaves inexistentes).
- [ ] **Step 4: Implementar** `Bloco`, `CATALOGO`, `eh_cumprimento`; atualizar a docstring de `sinais.py` (lista de blocos).
- [ ] **Step 5: Rodar os dois arquivos** → PASS. (`test_pontuacao`, `test_planilha` e `test_casos` podem quebrar por `Bloco`; são corrigidos nas Tasks 3 e 5. Se `test_casos` usa `PATRIMONIO`, trocar por `IMOVEL` aqui.)
- [ ] **Step 6: Commit** `feat: add settlement and final-judgment signals, turn vulnerability into discounts`

### Task 2: Acordo em outro processo

**Files:**
- Modify: `src/guicredito/djen/casos.py` (nova `marcar_acordos`, docstring)
- Test: `tests/djen/test_casos.py`

**Interfaces:**
- Consumes: `Bloco.ACORDO`, chave `acordo_homologado` (Task 1).
- Produces: `marcar_acordos(casos: list[Caso], referencia: Iterable[Caso]) -> list[Caso]`. Devolve `casos` na mesma ordem; casos com acordo de um mesmo devedor em **outro** número de processo de `referencia` ganham um `Sinal("acordo_outro_processo", Bloco.ACORDO, 30, "acordo em outro processo", f"Acordo homologado no processo {formatar_cnj(numero)}")` (o primeiro número em ordem crescente) via `dataclasses.replace`. Uma vez por caso.

Regras: o devedor do caso é `caso.devedor.split("; ")` (só pessoas; `None` = nenhum). Chave = `normalizar(nome)`. Só nomes com ≥3 palavras na forma normalizada. `referencia` pode conter o próprio `caso` e duplicatas do mesmo número — o próprio número nunca conta.

- [ ] **Step 1: Escrever testes** (usar o helper `caso(...)` do arquivo ou criar um igual ao de `test_pontuacao.py`, com `sinais=(Sinal("acordo_homologado", Bloco.ACORDO, 0, "x", "t"),)` para o processo do acordo):
  - `test_acordo_em_A_pontua_B_e_nao_A`: A e B com devedor "JOSÉ CARLOS DA SILVA", acordo em A → B tem sinal de 30 com trecho citando o CNJ formatado de A; A não tem.
  - `test_nome_com_acento_e_espaco_diferentes_casa`: A "JOSÉ CARLOS DA SILVA", B "Jose Carlos da  Silva" → B marcado.
  - `test_nome_de_duas_palavras_nao_casa`: "JOSÉ SILVA" nos dois → nada.
  - `test_segundo_devedor_conta`: B com devedor "MARIA EXEMPLO; JOSÉ CARLOS DA SILVA" → marcado.
  - `test_mesmo_numero_no_historico_nao_conta`: `referencia=[A, A_historico]` com o mesmo número e acordo só em `A_historico` → A não marcado.
  - `test_devedor_none_nao_quebra`: caso com `devedor=None` passa intacto.
- [ ] **Step 2: Rodar** `.venv/bin/python -m pytest tests/djen/test_casos.py -v` → FAIL (`marcar_acordos` não existe).
- [ ] **Step 3: Implementar `marcar_acordos`** em `casos.py` (importar `formatar_cnj` de `texto`). Montar `dict[str, set[str]]` nome→números com acordo a partir de `referencia`, depois marcar.
- [ ] **Step 4: Rodar** → PASS.
- [ ] **Step 5: Commit** `feat: score debtors who settled in another case`

### Task 3: Pontuação nova

**Files:**
- Modify: `src/guicredito/djen/modelos.py` (`Pontuacao`)
- Modify: `src/guicredito/djen/pontuacao.py` (tabelas, `pontuar`, nova `recente`, docstring)
- Test: `tests/djen/test_pontuacao.py`

**Interfaces:**
- Consumes: `Bloco` (Task 1), `partes.eh_cumprimento` (Task 1), sinal `acordo_outro_processo` (Task 2).
- Produces: `Pontuacao(acordo_anterior, imovel, transito, desgaste, veiculo, credor, descontos, total)` — todos `int`, nessa ordem.
- Produces: `pontuar(caso: Caso) -> Pontuacao` (o parâmetro `ano_atual` sai: idade não pontua mais).
- Produces: `recente(caso: Caso, ano_atual: int) -> bool` — `True` quando `caso.ano_divida != 0 and ano_atual - caso.ano_divida < 1`.

Valores: `TETO_BLOCO = {ACORDO: 30, IMOVEL: 25, TRANSITO: 15, DESGASTE: 15, VEICULO: 3}`. `PONTOS_CREDOR = {FUNDO: 5, PESSOA: 5, EMPRESA: 5}` (banco ausente → 0; nunca chega aqui). Trânsito: soma do bloco com teto; se der 0 e `eh_cumprimento(caso.classe)`, vale 10. `DESCONTO_SEM_DEVEDOR = 15` mantido. Total = soma de tudo, mínimo 0. `ordenar` não muda.

- [ ] **Step 1: Reescrever os testes** de `test_pontuacao.py` (default do helper: `tipo_credor=TipoCredor.EMPRESA`, `credor="EMPRESA EXEMPLO LTDA"`):
  - `test_exemplo_completo`: sinais `acordo_outro_processo` ACORDO 30, `imovel_penhorado` IMOVEL 15, `bloqueio_negativo` DESGASTE 10, `veiculo` VEICULO 3, `gratuidade_devedor` DESCONTO −5 → `Pontuacao(30, 15, 0, 10, 3, 5, -5, 58)`.
  - `test_tetos_por_bloco`: IMOVEL 20+15 → 25; DESGASTE 10+10+8 → 15; TRANSITO 15 → 15.
  - `test_cumprimento_sem_frase_vale_10` / `test_cumprimento_com_frase_vale_15` / `test_execucao_sem_frase_vale_0`.
  - `test_credor` parametrizado: FUNDO/PESSOA/EMPRESA → 5, `None` → 0.
  - `test_recente`: `recente(caso(ano_divida=2026), 2026)` True; 2025 → False; `ano_divida=0` → False.
  - Manter `test_descontos_e_alerta`, `test_total_nunca_negativo`, `test_ordenar_...` com a `Pontuacao` de 8 campos.
- [ ] **Step 2: Rodar** `.venv/bin/python -m pytest tests/djen/test_pontuacao.py -v` → FAIL.
- [ ] **Step 3: Implementar** `Pontuacao`, `pontuar`, `recente`; remover `_pontos_idade`; atualizar docstring.
- [ ] **Step 4: Rodar** → PASS.
- [ ] **Step 5: Commit** `feat: rescore cases in the order set at the 13/11 meeting`

### Task 4: Pipeline — filtros, histórico e resumo

**Files:**
- Modify: `src/guicredito/djen/fonte.py` (nova `dias_uteis_antes`)
- Modify: `src/guicredito/djen/modelos.py` (`ResumoRodada`)
- Modify: `src/guicredito/djen/pipeline.py` (`rodar`, `parse_args`, `main`, docstring)
- Test: `tests/djen/test_fonte.py`, `tests/djen/test_pipeline.py`

**Interfaces:**
- Consumes: `marcar_acordos` (Task 2), `pontuar(caso)`, `recente(caso, ano)` (Task 3).
- Produces: `fonte.dias_uteis_antes(inicio: date, n: int) -> list[date]` — os `n` dias úteis estritamente antes de `inicio`, em ordem crescente; `n=0` → `[]`.
- Produces: `ResumoRodada` ganha `processos_banco: int`, `processos_recentes: int`, `dias_historico: int` (dias de histórico efetivamente lidos), depois de `processos_so_empresa`.
- Produces: `rodar(..., historico: int = 0)`; `parse_args` aceita `--historico` (int, padrão 0).

Ordem em `rodar`: baixar período (como hoje) → baixar histórico (`dias_uteis_antes(inicio, historico)`; dia sem caderno imprime `sem caderno em dd/mm` e não entra em `dias_sem_caderno`) → ler e resumir cobrança dos dois (contadores `publicacoes_*` só do período) → `casos = montar_casos(periodo)`, `casos_hist = montar_casos(historico)` → `casos = marcar_acordos(casos, casos + casos_hist)` → fora: `so_empresa`, depois `tipo_credor is BANCO`, depois `recente(caso, momento.year)` (cada um conta no seu contador, na ordem) → `pontuar` → `ordenar`. `_publicacoes_dos_casos` só lê os cadernos do período. `main` imprime duas linhas novas: `Fora por credor banco: N` e `Fora por ter menos de 1 ano: N`, e `Dias de histórico: N` quando `--historico` > 0.

- [ ] **Step 1: Testes em `test_fonte.py`**: `dias_uteis_antes(date(2026, 11, 9), 3) == [date(2026, 11, 4), date(2026, 11, 5), date(2026, 11, 6)]` (9/11 é segunda); `dias_uteis_antes(date(2026, 11, 9), 0) == []`.
- [ ] **Step 2: Ajustar `test_rodar_ponta_a_ponta`**: credor de PROC_A e PROC_E passa a `"EMPRESA EXEMPLO LTDA"`; adicionar PROC_F com credor `"BANCO EXEMPLO S.A."` e devedor pessoa → `resumo.processos_banco == 1`, fora da planilha. Demais asserts conferidos contra o resultado novo.
- [ ] **Step 3: Testes novos em `test_pipeline.py`**:
  - `test_caso_do_ano_corrente_fica_fora`: processo `...20268260...` (ano 2026) com `agora` em 2026 → `processos_recentes == 1`, não está na planilha.
  - `test_historico_acha_acordo`: histórico de 1 dia (06/11) com processo X, devedor "JOSÉ CARLOS DA SILVA", texto "Homologo o acordo"; período 09/11 com processo Y do mesmo devedor, credor empresa → `rodar(..., historico=1)`; na aba Casos, Y está e a coluna "Sinais de patrimônio" contém "acordo em outro processo"; X não está na planilha; `resumo.dias_historico == 1`.
  - `test_historico_sem_caderno_segue`: `historico=1` sem metadados para o dia anterior → roda, `dias_historico == 0`, `dias_sem_caderno == []`.
  - `test_parse_args` cobre `--historico 20` → `args.historico == 20`, padrão 0.
- [ ] **Step 4: Rodar** `.venv/bin/python -m pytest tests/djen/test_fonte.py tests/djen/test_pipeline.py -v` → FAIL.
- [ ] **Step 5: Implementar** `dias_uteis_antes`, campos de `ResumoRodada`, `rodar`, `parse_args`, `main`; atualizar docstring de `pipeline.py`.
- [ ] **Step 6: Rodar** → PASS (planilha pode precisar da Task 5 para o assert da coluna; se sim, fazer a Task 5 antes deste passo e voltar).
- [ ] **Step 7: Commit** `feat: drop bank and under-one-year cases, add --historico lookback`

### Task 5: Planilha e documentação

**Files:**
- Modify: `src/guicredito/djen/planilha.py` (`_COLUNAS`, `_EXPLICACAO`, `_PONTOS`, `_aba_casos`, `_aba_como_ler`, docstring)
- Modify: `READING.md` (itens 11 e 13), `docs/superpowers/specs/2026-11-08-djen-casos-design.md` (uma linha no topo da seção 9 apontando para o design de 22/11)
- Test: `tests/djen/test_planilha.py`

**Interfaces:**
- Consumes: `Bloco`, `Pontuacao` de 8 campos, `ResumoRodada` novo.

Colunas: igual a hoje, trocando `"Sinais de vulnerabilidade"` por `"Alertas"`. Conteúdo: "Sinais de desgaste" = DESGASTE; "Sinais de patrimônio" = ACORDO, IMOVEL, TRANSITO, VEICULO; "Alertas" = DESCONTO, ALERTA. Explicações dessas três colunas e de "Tipo de credor" (`"Fundo ⚑, Pessoa ou Empresa. Vazio se não houver credor. Bancos ficam fora."`) atualizadas. `_PONTOS` reescrito com exatamente estas linhas:

```
Acordo em outro processo (máx. 30): o mesmo devedor tem acordo homologado em outro processo lido na rodada 30. Só nomes com 3 palavras ou mais.
Imóvel (máx. 25): leilão negativo 20; imóvel penhorado, matrícula ou avaliação 15; bem de família 8; penhora 6.
Trânsito em julgado (máx. 15): texto cita trânsito em julgado 15; cumprimento de sentença sem essa frase 10.
Desgaste (máx. 15): bloqueio ou pesquisa com resultado negativo 10; acordo frustrado 10; arquivamento provisório 8.
Veículo (máx. 3): Renajud ou veículo 3.
Credor (máx. 5): Empresa, Pessoa ou Fundo 5. Credor banco fica fora da planilha.
Idade: processo com menos de 1 ano fica fora. A idade não soma pontos.
Descontos, sem teto: superendividamento −10; ausência de bens ou art. 921 −10; prescrição intercorrente −10; Defensoria −5; justiça gratuita deferida ao devedor −5; devedor não identificado −15.
Alerta, sem pontos: devedor não localizado; idoso(a); salário ou aposentadoria impenhorável.
O total nunca fica abaixo de 0. Dentro de cada bloco, os pontos somam até o máximo do bloco.
```

Como ler ganha, depois de "Fora por serem só empresa": `["Fora por credor banco", resumo.processos_banco]`, `["Fora por ter menos de 1 ano", resumo.processos_recentes]`, e `["Dias de histórico lidos", resumo.dias_historico]`.

- [ ] **Step 1: Ajustar `test_planilha.py`**: `CABECALHO` com "Alertas"; helper `pontuado` com `Pontuacao(0, 0, 0, 0, 0, 0, 0, total)`; `rodada()` com os três campos novos. Testes novos: sinal IMOVEL e sinal `acordo_outro_processo` aparecem em "Sinais de patrimônio"; sinal DESCONTO "⚠ Defensoria Pública" aparece em "Alertas"; a aba Como ler contém a linha "Credor (máx. 5): ..." e a linha "Fora por credor banco".
- [ ] **Step 2: Rodar** `.venv/bin/python -m pytest tests/djen/test_planilha.py -v` → FAIL.
- [ ] **Step 3: Implementar** as mudanças em `planilha.py`; editar `READING.md` e a linha no spec de 08/11.
- [ ] **Step 4: Rodar a suíte inteira** `.venv/bin/python -m pytest -q` → todos passam.
- [ ] **Step 5: Commit** `feat: show the new score blocks on the workbook`

### Task 6: Rodada real e conferência das frases

**Files:** nenhum de código, salvo ajuste de regex se a rodada mostrar falso positivo (com teste).

- [ ] **Step 1:** Rodar contra os cadernos já baixados em `/Users/nick/Desktop/projects/claude_euler/projects/GUICredito/dados/cadernos` (02 a 06/11/2026): `.venv/bin/python -c "from datetime import date; from pathlib import Path; from guicredito.djen.pipeline import rodar; print(rodar(date(2026,11,3), date(2026,11,6), historico=1, pasta_dados=Path('/Users/nick/Desktop/projects/claude_euler/projects/GUICredito/dados/cadernos'), pasta_saida=Path('saida')))"`. Esperado: planilha em `saida/`, nenhum credor banco.
- [ ] **Step 2:** Ler os 30 primeiros "trecho" de `acordo_homologado` e `transito_em_julgado` na aba Publicações. Se algum for texto-padrão, adicionar a frase a `PADROES` com teste de "não pontua" (trecho sem nomes) e commit `fix: ignore TJSP boilerplate for ...`.
- [ ] **Step 3:** Relatar ao Nick: funil (lidas, cobrança, processos, fora por empresa/banco/recente, na planilha), quantos casos ganharam "acordo em outro processo", e os 5 primeiros da lista sem nomes no relatório do terminal.
