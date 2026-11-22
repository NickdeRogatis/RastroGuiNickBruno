# Reading the new score (22/11/2026)

Read this file to see what changed in the score after the 13/11 meeting, and in what order to read it. [READING.md](READING.md) is still the map of the whole command. This page covers only what changed.

Commits `f7dbd37` to `d63c248` on `feature/djen-casos`. To see the full diff in PyCharm: Git → Log, select those 8 commits, or run `git diff 3d8d0f7 d63c248`.

## Change marks

| Mark | Meaning |
|---|---|
| 🆕 | New: did not exist before |
| ✏️ | Changed: same thing, new rule or new numbers |
| ❌ | Removed |
| 🐞 | Fix found in the first real run (04–06/11), after the planned work |

Line numbers are for commit `d63c248`.

## Read in this order

The first two files explain why. Then follow the score from the phrase in the gazette to the cell in Excel.

### 1. [docs/superpowers/specs/2026-11-22-score-reuniao-design.md](docs/superpowers/specs/2026-11-22-score-reuniao-design.md) 🆕

Sections 1 and 5 first. Why the score changed (buy good credit, no banks) and the new points table. The 08/11 spec's section 9 now has a line at the top pointing here ✏️.

### 2. [src/guicredito/djen/modelos.py](src/guicredito/djen/modelos.py) ✏️

The nouns the other files share.

- ✏️ `Bloco` (line 28): now `ACORDO`, `IMOVEL`, `TRANSITO`, `DESGASTE`, `VEICULO`, `DESCONTO`, `ALERTA`.
- ❌ `Bloco.PATRIMONIO` and `Bloco.VULNERABILIDADE`: gone. Real estate and vehicle are separate blocks now. The vulnerability signals became discounts or alerts.
- ✏️ `Pontuacao` (line 118): eight fields in the meeting's order: `acordo_anterior`, `imovel`, `transito`, `desgaste`, `veiculo`, `credor`, `descontos`, `total`.
- ❌ `Pontuacao.idade`, `.patrimonio`, `.vulnerabilidade`: gone.
- 🆕 `ResumoRodada.processos_banco`, `.processos_recentes`, `.dias_historico` (line 145): the new funnel counts.

### 3. [src/guicredito/djen/sinais.py](src/guicredito/djen/sinais.py) ✏️

The phrases that earn or lose points. Read `CATALOGO` (line 40).

- 🆕 `acordo_homologado` (line 66): "homologo o acordo", "fica homologado o acordo", "acordo homologado". Worth **0** in its own case. `casos.py` turns it into points on the debtor's *other* cases.
- 🆕 `transito_em_julgado` (line 76): 15 points. Only past-tense phrases count: "transitou em julgado", "acórdão transitado em julgado", "certifico o trânsito em julgado".
- ✏️ Real estate signals now use `Bloco.IMOVEL`: failed auction 20, seized or appraised property 15, **bem de família 12 → 8**, generic seizure 6.
- ✏️ `veiculo`: **4 → 3**, own block `VEICULO`.
- ✏️ `superendividamento` (line 124): **+15 → −10**.
- ✏️ `gratuidade_devedor` and `defensoria`: **+8 → −5**.
- ✏️ `idoso` (line 150) and `salario_impenhoravel`: **+8 / +6 → 0, alert only**.
- 🐞 Settlement regex tightened. The first version caught "de acordo com a classificação" and lists of example filings.
- 🐞 Final-judgment regex tightened. The first version caught "certificado o trânsito em julgado, arquivem-se", which describes a future step.
- 🐞 `PADROES` lines 36–37: two TJSP templates masked, "cumprimento de sentença relativo a acordo homologado" and "[penhora de imóvel] se houver requerimento de penhora de imóvel".

### 4. [src/guicredito/djen/partes.py](src/guicredito/djen/partes.py) ✏️

- 🆕 `eh_cumprimento` (line 86): true for cumprimento de sentença classes. `pontuacao.py` uses it for the 10-point final-judgment fallback.
- 🐞 `_ENTIDADE` (line 48), used by `_empresa_pelo_nome` (line 99): public bodies, cooperatives, foundations, clubs, churches and "S A" are no longer treated as people. In the first real run, INSS, the city government, the state treasury and Unimed were debtors "of type person", so their many settlements marked 292 of 300 cases. After the fix it is 48 cases from 43 different people.

### 5. [src/guicredito/djen/casos.py](src/guicredito/djen/casos.py) ✏️

- 🆕 `marcar_acordos` (line 203): the "already settled in another case" rule. It collects debtors with `acordo_homologado` from every case read (including history days), then adds a 30-point `acordo_outro_processo` signal to each of their *other* cases. The signal's text names the case where the settlement happened.
- 🆕 `_nomes_para_cruzar` (line 196) and `_PALAVRAS_MINIMAS = 3` (line 45): names are compared after `normalizar` (no accents, lowercase, single spaces), and only with three words or more, so "JOSÉ SILVA" never matches.
- ✏️ Module docstring (line 14): explains the new step.

### 6. [src/guicredito/djen/pontuacao.py](src/guicredito/djen/pontuacao.py) ✏️

Short. The whole score in one place.

- ✏️ `PONTOS_CREDOR` (line 22): company, person and fund all **5**. Bank is gone from the table because bank cases never get here.
- ✏️ `TETO_BLOCO` (line 27): settlement 30, real estate 25, final judgment 15, wear **25 → 15**, vehicle 3.
- 🆕 `PONTOS_CUMPRIMENTO = 10` (line 34): a cumprimento de sentença with no final-judgment phrase still gets 10.
- 🆕 `recente` (line 46): true when the case is under 1 year old. `ano_divida == 0` (year unknown) is never recent.
- ✏️ `pontuar` (line 50): no longer takes `ano_atual`. Age adds no points.
- ❌ `_pontos_idade`: gone (was up to 20 points).

### 7. [src/guicredito/djen/fonte.py](src/guicredito/djen/fonte.py) ✏️

- 🆕 `dias_uteis_antes` (line 84): the N weekdays before a date. Used by `--historico`.

### 8. [src/guicredito/djen/pipeline.py](src/guicredito/djen/pipeline.py) ✏️

Read `rodar` (line 50) again.

- 🆕 History download (line 73): `historico` extra weekdays before `--inicio`, read only to find settlements. Their cases never go on the sheet. A day with no caderno prints `sem caderno em dd/mm` and the run goes on.
- 🆕 `marcar_acordos` call (line 93).
- 🆕 Bank filter (line 96): a case whose main creditor is a bank is dropped before scoring.
- 🆕 Under-1-year filter (line 98).
- ✏️ `pontuar(caso)` (line 100): no year argument.
- 🆕 `--historico N` in `parse_args` (line 144). Default 0. Negative numbers are rejected.
- 🆕 `main` (line 169) prints three new lines: history days, bank cases dropped, under-1-year cases dropped.

### 9. [src/guicredito/djen/planilha.py](src/guicredito/djen/planilha.py) ✏️

- ✏️ `_COLUNAS` (line 41): "Sinais de vulnerabilidade" → **"Alertas"**.
- ✏️ Column content (line 164): "Sinais de desgaste" is wear only. "Sinais de patrimônio" is settlement in another case, real estate, final judgment and vehicle. "Alertas" is discounts and alerts (⚠).
- ✏️ `_PONTOS` (line 75): the Como ler tab's points table, rewritten to match the spec.
- 🆕 Como ler funnel (line 247): "Fora por credor banco", "Fora por ter menos de 1 ano", "Dias de histórico lidos".

### 10. Tests, after the module they lock in

They use fictional names and never touch the network.

- [tests/djen/test_sinais.py](tests/djen/test_sinais.py) ✏️: the `DETECTAR` and `NAO_DETECTAR` tables have the new points. 🐞 rows show the boilerplate that must *not* score.
- [tests/djen/test_partes.py](tests/djen/test_partes.py) ✏️: 🆕 `test_eh_cumprimento` (line 130). 🐞 `test_orgao_publico_e_cooperativa_nao_sao_pessoa` (line 156) and `test_nome_de_pessoa_continua_pessoa` (line 162).
- [tests/djen/test_casos.py](tests/djen/test_casos.py) ✏️: 🆕 the six `marcar_acordos` tests from line 169. Read `test_acordo_em_a_pontua_b_e_nao_a` first.
- [tests/djen/test_pontuacao.py](tests/djen/test_pontuacao.py) ✏️: rewritten. `test_exemplo_completo` (line 50) adds up one case block by block: 30 + 15 + 0 + 10 + 3 + 5 − 5 = 58.
- [tests/djen/test_fonte.py](tests/djen/test_fonte.py) ✏️: 🆕 `test_dias_uteis_antes`.
- [tests/djen/test_pipeline.py](tests/djen/test_pipeline.py) ✏️: creditors in the old tests are now companies, plus a bank case that must drop out. 🆕 `test_caso_do_ano_corrente_fica_fora` (line 191), `test_historico_acha_acordo` (line 207), `test_historico_sem_caderno_segue` (line 239).
- [tests/djen/test_planilha.py](tests/djen/test_planilha.py) ✏️: new header, eight-field `Pontuacao`, and where each signal lands.

### 11. The result

[saida/casos_djen_2026-11-04_a_2026-11-06.xlsx](saida/casos_djen_2026-11-04_a_2026-11-06.xlsx), not in git (names). Run of 04–06/11 with `historico=2`: 144,140 cases read, 25,635 company-only, 18,865 bank, 22,301 under 1 year, 300 on the sheet. 239 have real estate, 48 have a settlement in another case, 18 have a final judgment. The highest score is 69, so no case is green yet.

## Not read again

- [docs/superpowers/plans/2026-11-22-score-reuniao.md](docs/superpowers/plans/2026-11-22-score-reuniao.md) 🆕: the build recipe. You do not need it to see what the code does.
- [READING.md](READING.md) ✏️: items 5, 11, 12 and 13 and the "Second pass" section were updated for the new score.
