# Comandos do GUICredito no Mac Studio

## Comece pelo piloto da posição 3

Para **ver o resultado que já existe**, cole estas duas linhas no Terminal do PyCharm (menu **View → Tool Windows → Terminal**) ou no Terminal do Mac. O HTML abre no navegador.

~~~zsh
cd /Users/nickderogatis/Desktop/RastroGuiNickBruno
open saida/pessoas/piloto_posicao_03_advogados-do-credor/relatorio.html
~~~

Para **rodar o código**, prepare o mesmo terminal uma vez. Repita este bloco ao abrir outra aba. O interpretador está na pasta `.venv` do projeto.

~~~zsh
cd /Users/nickderogatis/Desktop/RastroGuiNickBruno
export PYTHONPATH="$PWD/src"
py=.venv/bin/python
planilha=saida/casos_djen_2026-11-12_a_2026-11-23.xlsx
piloto=saida/aprofundamento/piloto_posicao_03
top10=saida/aprofundamento/2026-11-23_top10
lote=saida/pessoas/piloto_posicao_03_advogados-do-credor
~~~

| O que você quer fazer agora | Comando no terminal preparado |
|---|---|
| Conferir o escopo e o destino, sem enviar consultas | `"$py" -u "$piloto/testar_hermes.py" --prever` |
| Pesquisar os **dois advogados do credor** ou retomar a leitura pendente | `"$py" -u "$piloto/testar_hermes.py"` |
| Conferir a variação que inclui **só a empresa credora**, sem enviar consultas | `"$py" -u "$piloto/testar_hermes.py" --refazer-credora --prever` |
| Autorizar nova tentativa da credora, cuja busca antiga ficou sem URLs salvas | `"$py" -u "$piloto/testar_hermes.py" --refazer-credora` |
| Abrir o resultado da credora depois dessa execução | `open saida/pessoas/piloto_posicao_03_credor/relatorio.html` |
| Abrir a planilha privada dos advogados | `open "$lote/pessoas.xlsx"` |
| Abrir a versão para revisão | `open "$lote/revisao.html"` |
| Mostrar o relatório dos advogados no Finder | `open -R "$lote/relatorio.html"` |

O atalho `testar_hermes.py` fica em `saida/` neste Studio e está vinculado ao processo da posição 3. Ele carrega a chave localmente e usa uma pasta distinta para cada escopo. Repetir o mesmo comando reutiliza as buscas concluídas. Para outro processo ou outro checkout, use os comandos por módulo abaixo.

No botão **Run** do PyCharm, crie uma configuração **Python**. Use a raiz do projeto como *Working directory*, `.venv/bin/python` como interpretador e o arquivo `saida/aprofundamento/piloto_posicao_03/testar_hermes.py` como *Script path*. Em *Environment variables*, defina `PYTHONPATH=/Users/nickderogatis/Desktop/RastroGuiNickBruno/src`. Comece com `--prever` em *Script parameters*. Para executar a busca dos advogados, deixe esse campo vazio.

## 1. Gerar a planilha de processos no DJEN

Para abrir a planilha do piloto, use `open "$planilha"`. Só gere uma planilha quando quiser outra rodada. Rodar novamente com as mesmas datas grava no mesmo arquivo, e uma mudança na planilha de origem pode afetar a retomada do lote.

**Período automático.** Coleta os cinco últimos dias de segunda a sexta até ontem e classifica até 300 processos do TJSP.

~~~zsh
"$py" -m guicredito.djen
~~~

**Período escolhido.** Informe início e fim juntos. Este exemplo usa outro período. Troque as datas para escolher a sua rodada.

~~~zsh
"$py" -m guicredito.djen --inicio 2026-11-03 --fim 2026-11-06
~~~

**Histórico, limite e tribunal.** Este exemplo grava até 100 casos e examina cinco dias úteis anteriores para identificar acordos em outros processos. O histórico adicional serve ao cálculo do score. O limite define o número de linhas da aba **Casos**.

~~~zsh
"$py" -m guicredito.djen --inicio 2026-11-03 --fim 2026-11-06 \
  --historico 5 --limite 100 --tribunal TJSP
~~~

Os cadernos ficam em `dados/cadernos/`. A saída é `saida/casos_djen_AAAA-MM-DD_a_AAAA-MM-DD.xlsx`. Para usar outra planilha nas próximas etapas, ajuste a variável `planilha`.

## 2. Aprofundar um ou até dez processos no TJSP

**Lote já coletado.** Abra o relatório dos dez casos da rodada. Para retomar uma consulta interrompida, use o segundo comando com a mesma seleção e pasta. A consulta reaproveita resultados compatíveis que já estejam coletados ou parcialmente coletados.

~~~zsh
open "$top10/relatorio.html"
~~~

~~~zsh
"$py" -m guicredito.aprofundamento consultar \
  --selecao "$top10/selecionados.json" --saida "$top10" --intervalo 5
~~~

**Lote novo.** Na aba **Casos**, confira **Pontos** e escolha os valores da coluna **#**. Para casos com mais de 50 pontos, escolha as posições que atendem a esse corte. `--posicoes 1-10` seleciona as dez primeiras posições independentemente da pontuação. Outras formas válidas são `3`, `1,3,7` e `1-3,7`. O limite é de dez posições distintas por seleção.

~~~zsh
base=saida/aprofundamento/rodada_posicoes_1_3_7
"$py" -m guicredito.aprofundamento selecionar \
  --planilha "$planilha" --posicoes 1,3,7 --destino "$base/selecionados.json" &&
"$py" -m guicredito.aprofundamento consultar \
  --selecao "$base/selecionados.json" --saida "$base" --intervalo 5
~~~

Use uma pasta nova ao trocar a seleção. Para retomar a mesma, repita apenas `consultar`. O intervalo padrão é de 5 segundos e o mínimo é 3. O comando salva `selecao.json`, `resumo.json`, um diretório por processo e `relatorio.html`. O código de saída 2 também pode indicar coleta parcial. Consulte o relatório para identificar o caso pendente.

**Reprocessar respostas salvas** atualiza a extração e o relatório localmente.

~~~zsh
"$py" -m guicredito.aprofundamento reprocessar --saida "$top10"
~~~

**Importar HTML do e-SAJ** aproveita a página salva manualmente para um processo da seleção. Substitua o caminho do HTML.

~~~zsh
"$py" -m guicredito.aprofundamento importar \
  --selecao "$top10/selecionados.json" --saida "$top10" \
  --processo 1012087-18.2017.8.26.0020 --html "/caminho/pagina-esaj.html"
~~~

## 3. Pesquisar a partir de qualquer aprofundamento

Escolha a pasta de entrada e o escopo. Estes valores apontam para os dois advogados do piloto e reutilizam a pasta do atalho. Para a seleção inteira dos dez, use `base="$top10"`. Para um lote novo, use a pasta da etapa 2. Mantenha a planilha que originou a seleção. Recalcule `lote` sempre que mudar `base` ou `alvos`.

~~~zsh
base="$piloto"
alvos=advogados-do-credor
lote="saida/pessoas/$(basename "$base")_${alvos}"
~~~

| Valor de `--alvos` | Quem entra na seleção |
|---|---|
| `advogados-do-credor` | Apenas os advogados identificados do lado do credor |
| `credor` | Apenas o credor |
| `polo-credor` | Credor e advogados do credor |
| `todos` | Todos os alvos identificados, inclusive do lado devedor. É o padrão da CLI quando a opção é omitida |

No piloto, use o escopo explícito dos advogados para manter a credora fora da rodada que já passou pelo script anterior. Cada pasta controla suas próprias buscas. Iniciar outro lote com alvos que já foram pesquisados pode repetir a consulta externa.

**Processar só os arquivos locais.** Gera os relatórios em uma pasta com sufixo `_local`. Use esta variação para conferir a lista de alvos antes de enviar nomes a uma busca externa.

~~~zsh
PESSOAS_BUSCA= "$py" -m guicredito.pessoas pesquisar \
  --selecao "$base/selecao.json" --aprofundamento "$base" \
  --planilha "$planilha" --alvos "$alvos" --saida "${lote}_local"
open "${lote}_local/relatorio.html"
~~~

**Usar o Hermes no Studio.** Cole a função abaixo uma vez no terminal preparado. Ela lê a credencial dedicada de `~/.hermes/.env` e a disponibiliza apenas ao comando executado. O cliente chama o agente `hermes-agent` na porta 8642. O Qwen permanece no llama.cpp local na porta 18434.

~~~zsh
pessoas_hermes() (
  set +x
  export PESSOAS_BUSCA=hermes
  export PESSOAS_HERMES_URL=http://127.0.0.1:8642/v1
  export PESSOAS_HERMES_MODELO=hermes-agent
  local chave
  chave=$(sed -nE "s/^API_SERVER_KEY=['\"]?([^'\"]+)['\"]?$/\\1/p" "$HOME/.hermes/.env") || return 1
  if [[ -z "$chave" ]]; then
    echo 'Chave dedicada ausente no arquivo do Studio.' >&2
    return 1
  fi
  export PESSOAS_HERMES_KEY="$chave"
  "$py" -m guicredito.pessoas "$@"
)
~~~

**Verificar a autenticação e o ID listado** consulta `/v1/models`, sem iniciar pesquisa.

~~~zsh
pessoas_hermes verificar
~~~

**Testar busca e leitura com assunto impessoal.** Este comando faz uma consulta externa sobre *Example Domain*, mostra backend, IDs e URLs e testa uma leitura pelo modelo local. O plugin usa `web_search` do Parallel e pede a leitura ao modelo sem ferramentas. A disponibilidade da busca depende da cota pública.

~~~zsh
"$py" -u integracoes/hermes/testar.py --env-hermes "$HOME/.hermes/.env"
~~~

**Pesquisar com o escopo escolhido ou retomar.** A busca externa envia a consulta nominal ao backend. Use esta variação para os alvos aprovados para pesquisa. Salve e feche `pessoas.xlsx` antes de atualizar o lote.

~~~zsh
pessoas_hermes pesquisar \
  --selecao "$base/selecao.json" --aprofundamento "$base" \
  --planilha "$planilha" --alvos "$alvos" --saida "$lote" --retomar-leituras
~~~

Na primeira execução, o programa busca os alvos elegíveis e salva as URLs. Na retomada, lê as páginas pendentes com as URLs já salvas. Se indicar **possível envio** e não houver retorno salvo, confira `consultas.json` na pasta do processo antes de qualquer nova busca. **Casos** e **Candidatos** são contagens do lote. Abra o relatório para ver quais consultas e leituras efetivamente produziram evidências.

~~~zsh
open "$lote/relatorio.html"
open "$lote/pessoas.xlsx"
open "$lote/revisao.html"
~~~

A mensagem **Índice CNPJ não configurado** se refere à fonte local de empresas. As fontes consultadas pelo Hermes aparecem no relatório. Os ajustes opcionais são `PESSOAS_HERMES_TIMEOUT` (padrão 180 segundos), `PESSOAS_INTERVALO` (5 segundos, mínimo 3) e `PESSOAS_HERMES_CONTEXTO` (262144 tokens). Esta última variável informa o contexto ao cliente.

## 4. Manter o gateway e acessar pelo laptop

No Studio, consulte o estado do serviço instalado. Escolha a ação conforme o estado. Parar ou reiniciar afeta a API e os demais canais do mesmo gateway.

| Ação no Studio | Comando |
|---|---|
| Ver a versão | `hermes --version` |
| Consultar o gateway existente | `hermes gateway status` |
| Iniciar o serviço se estiver parado | `hermes gateway start` |
| Parar em uma janela de manutenção | `hermes gateway stop` |
| Recarregar o serviço quando estiver ocioso | `hermes gateway restart` |

Se o diagnóstico listar o modelo, mas a pesquisa indicar política indisponível, confira o plugin com `hermes plugins list` e use o ensaio impessoal da etapa 3. O procedimento de instalação do plugin está no [guia de Pessoas](READING_PESSOAS.md#hermes-e-acesso-do-laptop).

**No laptop**, abra um terminal e deixe o SSH em execução. O comando usa a porta SSH 22 e encaminha a porta 8642 somente em loopback.

~~~zsh
ssh -NT -o ExitOnForwardFailure=yes \
  -L 127.0.0.1:8642:127.0.0.1:8642 nickderogatis@Nicks-Mac-Studio.local
~~~

No cliente do laptop, a URL base também é `http://127.0.0.1:8642/v1`. A chave precisa estar disponível localmente no cliente por um meio privado. O caminho `~/.hermes/.env` acima pertence ao Studio. Se a porta 8642 do laptop estiver ocupada, use `-L 127.0.0.1:18642:127.0.0.1:8642` e a URL `http://127.0.0.1:18642/v1`. Pressione **Ctrl+C** no terminal SSH para fechar o túnel. O teste de ponta a ponta depende de uma conexão iniciada pelo laptop.

## 5. Operações opcionais do lote de pessoas

Nos comandos abaixo, `lote` aponta para a pasta que contém `pessoas.xlsx`. Substitua os caminhos que começam por `/caminho/` pelos arquivos reais da operação.

**OAB.** Após conferência manual, preencha a aba **OAB** ou importe o registro profissional. O JSON aceita um objeto ou uma lista com `alvo_id`, `nome`, `oab`, `uf`, `url`, `data` em formato ISO e `dados_profissionais`.

~~~zsh
"$py" -m guicredito.pessoas importar-oab --lote "$lote" --arquivo /caminho/oab.json
~~~

**Índice CNPJ local.** Primeiro confira o espaço. O JSON de estimativas traz `tamanhos` em bytes por arquivo, `temporarios` e `indice_novo`. Com espaço suficiente, arquivos já obtidos e leiaute conferido, construa o índice usando a competência do snapshot. O exemplo usa outubro de 2026.

~~~zsh
indice="$PWD/dados/cnpj/indice.sqlite"
"$py" -m guicredito.pessoas preparar-cnpj --prever-espaco /caminho/estimativas.json --indice "$indice"
~~~

~~~zsh
"$py" -m guicredito.pessoas preparar-cnpj --snapshot /caminho/snapshot \
  --layout /caminho/layout.json --competencia 2026-10 --indice "$indice" &&
export PESSOAS_INDICE_CNPJ="$indice"
~~~

**Contatos e conciliação.** O piloto está sem provedor de contatos. `contatos` depende de provedor configurado e das duas marcações individuais na aba **Candidatos** (**Confirmado** e **Autorizar consulta paga**). O contato humano antes de eventual compra é restrito ao credor ou ao advogado dele.

~~~zsh
"$py" -m guicredito.pessoas contatos --lote "$lote"
~~~

Para um futuro pedido incerto, confira o ID em `pedidos` no JSON privado e o estado com o fornecedor. **Escolha uma única linha** conforme o resultado confirmado. Substitua `ID_DO_PEDIDO`. Somente `executado` recebe o arquivo da resposta.

~~~zsh
"$py" -m guicredito.pessoas conciliar --lote "$lote" --requisicao ID_DO_PEDIDO --resultado nao_executado
"$py" -m guicredito.pessoas conciliar --lote "$lote" --requisicao ID_DO_PEDIDO --resultado executado --arquivo /caminho/resposta.json
"$py" -m guicredito.pessoas conciliar --lote "$lote" --requisicao ID_DO_PEDIDO --resultado encerrar
~~~

**Descarte.** Após marcar **Descartar = sim** na aba **Casos**, salvar e fechar a planilha, este comando mostra a prévia e seu código.

~~~zsh
"$py" -m guicredito.pessoas descartar --lote "$lote"
~~~

A confirmação seguinte **exclui os dados gerados dos casos marcados neste lote**. Use-a somente se quiser aplicar a prévia conferida, substituindo o código.

~~~zsh
"$py" -m guicredito.pessoas descartar --lote "$lote" --confirmar CODIGO_DA_PREVIA
~~~

## 6. Ajuda, testes e instalação em outro checkout

~~~zsh
"$py" -m guicredito.djen --help
"$py" -m guicredito.aprofundamento --help
"$py" -m guicredito.pessoas --help
"$py" -m guicredito.pessoas pesquisar --help
~~~

Para consultar as opções de qualquer outro subcomando, acrescente `--help` depois do nome. Escolha o teste conforme a etapa.

| O que testar | Comando |
|---|---|
| Projeto principal completo | `"$py" -m pytest -q` |
| Classificação DJEN | `"$py" -m pytest -q tests/djen` |
| Aprofundamento TJSP | `"$py" -m pytest -q tests/aprofundamento` |
| Pesquisa de pessoas | `"$py" -m pytest -q tests/pessoas` |
| Fluxo de pessoas com casos fictícios e serviços simulados | `"$py" -m pytest -q tests/pessoas/test_integracao.py` |
| Plugin do gateway com testes locais | `"$py" -m pytest -q tests/pessoas/test_gateway_piloto.py` |

O Studio já tem um ambiente virtual. Em um **checkout novo**, com Python 3.12 ou superior, rode na raiz e depois use a preparação do terminal com o caminho desse checkout.

~~~zsh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
~~~

### Coletor de PDFs antigo em RastroCursor

Este projeto separado baixa o Caderno 3 da Capital e extrai atos dos PDFs para JSONL. Use um terminal próprio na subpasta e o ambiente virtual dela. Faça a instalação uma vez.

~~~zsh
cd /Users/nickderogatis/Desktop/RastroGuiNickBruno/RastroCursor
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
~~~

Ajuste a data para a edição desejada. Se o download retornar outra data, use a data efetivamente salva no comando `parse`.

~~~zsh
PYTHONPATH=src .venv/bin/python -m guicredito download --date 2025-07-22 --out data/raw
PYTHONPATH=src .venv/bin/python -m guicredito parse --date 2025-07-22 \
  --raw data/raw --out data/parsed --report data/reports
PYTHONPATH=src .venv/bin/python -m pytest -q
~~~
