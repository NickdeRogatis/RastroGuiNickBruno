# Pesquisa de pessoas no GUICredito

A etapa `guicredito.pessoas` lê a seleção do aprofundamento, as capas disponíveis e a planilha classificada. Produz um lote privado para Nick conferir quem é cada candidato e quais fatos têm apoio nas fontes. Um nome igual, um cargo ou o capital de uma empresa, isoladamente, não estabelecem que uma pessoa pode pagar uma dívida. A posição e a pontuação do DJEN são preservadas.

## Experimentar no Studio com dois casos fictícios

Na pasta que contém este guia, o teste abaixo cria a planilha de origem, as capas, um índice CNPJ diminuto e dois casos em um diretório temporário. Ele chama a CLI pelo mesmo ponto de entrada usado em operação. As respostas do Hermes e do fornecedor são simuladas em memória.

```sh
PYTHONPATH=src ../RastroGuiNickBruno/.venv/bin/python -m pytest tests/pessoas/test_integracao.py -q
PYTHONPATH=src ../RastroGuiNickBruno/.venv/bin/python -m guicredito.pessoas --help
```

Esses comandos usam o ambiente Python do checkout vizinho neste Mac. No PyCharm, selecione o interpretador desse ambiente, este worktree como diretório de trabalho e sua pasta `src` como raiz de código. Em um checkout com ambiente próprio, use `.venv/bin/python`.

## Primeira passagem e revisão

O comando `pesquisar` recebe quatro caminhos. Em `--selecao`, indique o JSON de seleção. Em `--aprofundamento`, indique a pasta com os resultados dos casos. Em `--planilha`, indique a planilha classificada correspondente. Em `--saida`, indique uma pasta vazia destinada ao lote ou a pasta do mesmo lote para retomar. No piloto, Nick seleciona até dois casos. A etapa aceita até dez.

Com `PESSOAS_BUSCA` vazia, o programa usa apenas os arquivos locais e registra a indisponibilidade das fontes opcionais. A passagem gratuita nunca chama o fornecedor de contatos. Salve e feche o Excel antes de cada comando. Para atualizar os relatórios após uma edição, repita `pesquisar` com os mesmos caminhos.

Para restringir um lote, use `pesquisar --alvos advogados-do-credor`, `--alvos credor` ou `--alvos polo-credor`. Cada escopo usa sua própria pasta de saída. A busca concluída grava os IDs e as URLs antes da primeira leitura. Se uma página interromper a leitura, feche a planilha e repita o comando na mesma pasta com `--retomar-leituras`. O programa retoma as páginas pendentes e preserva as evidências anteriores. Uma busca cujo envio continua incerto e sem retorno salvo exige conferência manual.

| Arquivo | Uso |
|---|---|
| `pessoas.xlsx` | Planilha privada. Em **Candidatos**, marque **Confirmado** e, separadamente, **Autorizar consulta paga** por candidato. Se inserir um CPF, use uma célula de texto para preservar zeros iniciais. |
| `relatorio.html` | Consulta privada das fontes, evidências e marcações. As referências remetem aos registros do caso. |
| `revisao.html` | Arquivo destinado ao revisor. Cada ficha tem um código de caso, fase, categorias de indícios e limitações. Um vínculo societário pendente aparece apenas como pendente. Depois de confirmado, o resumo pode mostrar a faixa de capital declarado da empresa. |
| Pasta do caso | Contém JSON privado das consultas, dos candidatos, dos contatos e das evidências. O campo `arquivo` identifica o recorte guardado e `sha256` permite verificar seus bytes. |

Antes da eventual compra do crédito, o contato humano previsto é exclusivamente com o credor ou o advogado que o representa. O programa não envia mensagens. Nick reservou a primeira rodada nominal para depois da avaliação jurídica das fontes gratuitas, dos dados reunidos, do resumo do revisor, do descarte e da retenção pelo Hermes.

## Hermes e acesso do laptop

O ensaio **impessoal anterior** no Studio registrou Hermes `v0.21.7+500.g8f81791`, agente `hermes-agent`, API em `http://127.0.0.1:8642/v1`. O Qwen3.6-35B-A3B-UD-Q4_K_M roda no Studio, no llama.cpp autenticado da porta 18434. A consulta impessoal à IANA executou `web_search` via Parallel e `web_extract` via Firecrawl. O ensaio não mediu saldo, cota disponível ou custo futuro. [Resultado público consultado](https://www.iana.org/help/example-domains)

Configure no ambiente da aplicação `PESSOAS_HERMES_URL`, `PESSOAS_HERMES_MODELO=hermes-agent` e a credencial dedicada em `PESSOAS_HERMES_KEY`. Caminho da chave no Studio: `~/.hermes/.env` (campo `API_SERVER_KEY`). A aplicação lê suas próprias variáveis de ambiente ou seu próprio arquivo local `.env`. Mantenha o arquivo com permissão exclusiva para o usuário. O nome do modelo é obrigatório no diagnóstico. O contexto configurado é de 262144 tokens, o tempo limite do gateway é de 180 s e a pausa padrão é de 5 s. Os ajustes são `PESSOAS_HERMES_CONTEXTO`, `PESSOAS_HERMES_TIMEOUT` e `PESSOAS_INTERVALO`.

No Terminal do PyCharm no Studio, a partir da raiz do projeto, este ensaio consulta “Example Domain” pela rota do Hermes e testa a leitura. Se a página pública de exemplo mudar, a leitura usa um trecho fictício identificado na saída. Mostra os IDs, o backend, as URLs e o resultado da leitura. A chave é lida em memória do arquivo indicado.

```sh
PYTHONPATH=src .venv/bin/python integracoes/hermes/testar.py --env-hermes ~/.hermes/.env
```

O comando `pessoas verificar` confirma apenas o acesso autenticado a `/v1/models`. Na pesquisa, o cliente confere o contrato em `GET /v1/guicredito/policy` e envia cada turno a `POST /v1/guicredito/responses`. O plugin usa o Qwen configurado no Studio para decidir a chamada. O dispatcher aceita exatamente uma chamada de ferramenta com a consulta autorizada e limite de três resultados. Ele invoca a ferramenta MCP `web_search` do Parallel pelo endpoint público anônimo. A disponibilidade depende da cota pública do fornecedor. Na leitura, o plugin pede ao modelo apenas texto e rejeita respostas com ferramentas. Um plugin ausente, uma configuração de modelo incompatível ou falha do provedor interrompe a operação. A aplicação registra os resultados da pesquisa nominal no relatório privado do lote.

Para instalar o plugin em outro Studio compatível, copie `__init__.py` e `plugin.yaml` de `integracoes/hermes/guicredito_pessoas/` para `~/.hermes/plugins/guicredito-pessoas/`, execute `hermes plugins enable guicredito-pessoas` e confira o ensaio. Se a rota ainda responder 404, verifique se o gateway está ocioso e use `hermes gateway restart` para registrar as rotas ao iniciar. O plugin pressupõe o provedor `llamacpp` servido em `http://127.0.0.1:18434/v1` e o acesso anônimo permitido na configuração do Hermes.

O operador do laptop pode usar o túnel abaixo. O SSH respondeu anteriormente na porta 22 do Studio (`192.168.15.10`). Login e encaminhamento iniciados pelo laptop ainda dependem de teste a partir dele. O cliente usa a mesma URL de loopback com o túnel aberto.

```sh
ssh -NT -o ExitOnForwardFailure=yes -L 127.0.0.1:8642:127.0.0.1:8642 nickderogatis@Nicks-Mac-Studio.local
```

No Studio, `hermes gateway status` consulta o serviço do usuário. Se estiver parado, `hermes gateway start` inicia esse serviço. Para uma parada planejada, use `hermes gateway stop`. Parar o gateway interrompe o atendimento da API e dos canais conectados. Para encerrar somente o túnel do laptop, pressione Ctrl+C no terminal do SSH. Os testes da implementação não precisaram iniciar nem parar o gateway.

## Registros locais de empresas e advogados

**CNPJ.** Nick escolhe a competência e confere o leiaute oficial e o espaço no SSD interno. O preparador lê arquivos locais já obtidos. Use `preparar-cnpj --prever-espaco ESTIMATIVAS.json --indice INDICE.sqlite` antes de baixar a base. O JSON de previsão traz `tamanhos` (mapa dos arquivos para seus tamanhos em bytes), `temporarios` e `indice_novo`. Uma previsão indeterminada ou insuficiente impede o preparo. Com os arquivos presentes, use `preparar-cnpj --snapshot PASTA --layout LAYOUT.json --competencia AAAA-MM --indice INDICE.sqlite`. Defina `PESSOAS_INDICE_CNPJ` com o caminho do SQLite concluído. A configuração de leiaute aceita arquivos CSV e ZIP particionados, nomes das tabelas, índices de coluna a partir de zero, separador, codificação, presença de cabeçalho e as estimativas de construção. Um exemplo completo para o snapshot fictício está em [test_cnpj.py](tests/pessoas/test_cnpj.py). A competência e os índices das colunas do exemplo pertencem à fixture.

**OAB.** A aba privada **OAB** lista nome, inscrição disponível e link do cadastro. Faça a conferência manual e preencha a inscrição com UF, os dados profissionais conferidos e a data. A pendência de um advogado permite continuar os demais casos. Como alternativa, `importar-oab --lote PASTA --arquivo REGISTRO.json` aceita um objeto ou uma lista com os campos `alvo_id`, `nome`, `oab`, `uf`, `url`, `data` (ISO) e `dados_profissionais`. Nome, link e alvo devem corresponder à linha privada do lote.

## Passagem de contatos e descarte

`contatos --lote PASTA` relê as marcações. O piloto é gratuito e vem sem fornecedor contratado. A segunda revisão jurídica acontece quando Nick escolher um fornecedor e puder avaliar a licença, a finalidade, os identificadores aceitos e o preço. A obtenção de contatos depende das duas marcações individuais. Se a identificação devolver vários homônimos, a aba **Provedor** guarda opções mínimas. Confirme uma delas, salve e feche o Excel e repita `contatos`. Um pedido que pode ter sido faturado fica em estado incerto e exige conciliação antes de qualquer repetição.

Para conciliar um pedido incerto com um futuro fornecedor, localize `requisicao` em `pedidos` no JSON privado do caso e confira o resultado daquele ID com o fornecedor. Use `conciliar --lote PASTA --requisicao ID --resultado RESULTADO`. A opção `nao_executado` libera uma tentativa posterior a ser iniciada por Nick. A opção `executado` exige `--arquivo RESPOSTA.json` com a resposta recuperada. A opção `encerrar` encerra o pedido sem nova tentativa. A conciliação registra o resultado localmente.

Para excluir um caso, marque **Descartar = sim** na aba **Casos**. Execute `descartar --lote PASTA` para conferir os códigos de revisão da seleção. Aplique com `descartar --lote PASTA --confirmar CODIGO`. Editar a planilha depois da prévia exige uma nova prévia. A confirmação remove as saídas geradas para o caso e referências cruzadas ao processo. A posição original fica suprimida em reexecuções do lote. A operação alcança os arquivos gerenciados por esta etapa. As entradas DJEN/e-SAJ, o índice CNPJ, cópias que já foram compartilhadas e históricos externos têm retenção própria.

Os comandos de escrita usam bloqueio por lote e recuperam publicações interrompidas na próxima abertura. Um envio Hermes com resultado incerto exige conferência, pois repeti-lo poderia executar a busca outra vez. Em caso de dúvida sobre a conclusão de uma fonte, consulte o estado em `consultas.json` e as limitações no relatório. Ausência de resultado não é evidência de insolvência.
