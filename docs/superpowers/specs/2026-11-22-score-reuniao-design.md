# Score novo a partir da reunião de 13/11: design

- **Data:** 22/11/2026
- **Status:** rascunho para aprovação do Nick
- **Base:** reunião "Wispr Flow Credit Acquisition Plan" (13/11/2026) e o design de 08/11 (`2026-11-08-djen-casos-design.md`), cuja seção 9 este documento substitui.

Convenção: **decisão do Nick** (dele ou da reunião) e *(escolha minha)*.

## 1. Intenção e porquê

A reunião mudou a tese. A primeira frente agora é **comprar crédito bom e cobrar** (**decisão do Nick**), não procurar o devedor mais desgastado. O score precisa subir quem tem capacidade e histórico de pagar e tirar os bancos da lista, porque comprar de banco exige acesso que uma PJ pequena e nova não tem (**decisão do Nick**).

Ordem de peso definida na reunião (**decisão do Nick**):

1. Devedor que já fez acordo em outros processos.
2. Imóvel.
3. Trânsito em julgado (execução de título e cumprimento de sentença).
4. Carro bem abaixo, porque some fácil.

A idade do processo pesava demais. Passa a ser só um mínimo de 1 ano (**decisão do Nick**).

## 2. Objetivos

- A planilha da mesma rodada sai sem nenhum caso de credor banco e com o topo puxado por acordo anterior, imóvel e trânsito em julgado.
- **Critério de sucesso:** o Nick revisa dois casos gerados pelo modelo novo, como ficou combinado na reunião, e os filtros fazem sentido para ele.

## 3. Fora desta mudança

- Fontes novas: IPTU e IPVA por CPF, cartórios, provedores pagos. A busca de acordo por CPF em provedor (Judit/Escavador) fica para os 2 ou 3 casos comprados.
- **Familiares pelo sobrenome no Facebook:** fica fora. Contraria a regra de terceiros do documento de 26/10 (seção 7): quem não deve não é pesquisado.
- **Bot que acha o dono da PJ e manda mensagem:** fica fora. Contraria o anti-objetivo "virar lista de abordagem" do design de 08/11.
- Valor da causa (o piso de 50 a 100 mil citado na reunião): o DJEN não traz esse valor de forma confiável.

## 4. Abordagens consideradas

| | Abordagem | Troca |
|---|---|---|
| 1 | Ajustar os pesos e manter os blocos atuais | Mudança mínima, mas desgaste + vulnerabilidade continuam valendo 40 pontos e empurram para o topo quem não tem como pagar. |
| **2** | **Refazer o score na ordem da reunião** | Mexe em `Pontuacao`, nas colunas e na aba Como ler, mas o score passa a medir a tese nova. **Escolhida pelo Nick.** |

Para o acordo em outros processos: **(a) cruzar nomes dentro do próprio diário** foi escolhido. (b) Provedor pago por CPF fica para depois (**decisão do Nick**).

## 5. O score novo

| Bloco | Máx. | Como pontua |
|---|---|---|
| Acordo em outro processo | 30 | Mesmo devedor tem, **em outro processo** do período lido, publicação com acordo homologado: 30 |
| Imóvel | 25 | Leilão negativo/deserto 20 · imóvel penhorado, matrícula ou avaliação 15 · bem de família 8 · penhora genérica 6 |
| Trânsito em julgado | 15 | Texto cita trânsito em julgado: 15 · classe cumprimento de sentença sem essa frase: 10 |
| Desgaste | 15 | Mesmos sinais de hoje (bloqueio negativo 10, acordo frustrado 10, arquivamento provisório 8), teto 15 |
| Veículo | 3 | Renajud ou veículo: 3 |
| Credor | 5 | Empresa 5 · pessoa 5 · fundo 5 (continua marcado ⚑) |
| Idade | filtro | Menos de 1 ano: fora da planilha. 1 ano ou mais: 0 pontos |

Pesos e tetos são *(escolha minha)*, seguindo a ordem da reunião. O máximo teórico é 93.

**Bancos:** caso cujo credor de maior precedência é banco sai da planilha antes do score, como hoje sai o caso só de empresa (**decisão do Nick**). Fundo continua *(escolha minha)*: é PJ, não banco.

**Descontos e alertas:**

| Situação | Efeito | Origem |
|---|---|---|
| Superendividamento | −10 | Era +15 em vulnerabilidade. Indica que não há como pagar *(escolha minha)* |
| Defensoria Pública | −5 | Era +8 *(escolha minha)* |
| Justiça gratuita deferida ao devedor | −5 | Era +8 *(escolha minha)* |
| Idoso · salário/aposentadoria impenhorável | 0, só alerta | Eram +8 e +6 *(escolha minha)* |
| Sem bens / art. 921 / execução frustrada | −10 | Mantido |
| Prescrição intercorrente | −10 | Mantido |
| Devedor não identificado | −15 | Mantido |
| Devedor não localizado | 0, só alerta | Mantido |

O bloco vulnerabilidade deixa de existir. A regra dos textos-padrão do TJSP (não pontuam) continua valendo para todos os sinais, novos e antigos.

## 6. Como o acordo em outro processo é detectado

- Sinal novo `acordo_homologado` em `sinais.py`, detectado por publicação: frases como "homologo o acordo", "homologado o acordo", "acordo celebrado entre as partes". O sinal sozinho **não pontua** no próprio processo, porque acordo homologado no próprio caso normalmente quer dizer que ele já acabou.
- Depois de `montar_casos`, uma passada junta os devedores pessoa física pelo nome normalizado (`texto.normalizar`). Se um nome tem `acordo_homologado` em um processo, os **outros** processos desse nome ganham o bloco "Acordo em outro processo", com o número do processo do acordo no trecho.
- **Homônimos** *(escolha minha)*: só casa nome com pelo menos três palavras. "JOSÉ SILVA" não casa, "JOSÉ CARLOS DA SILVA" casa. Fica registrado como risco conhecido.
- **Janela:** a passada usa todas as publicações de cobrança lidas na rodada, não só as 300 do topo. Opção nova `--historico N` *(escolha minha)*: baixa N dias úteis antes de `--inicio` e usa esses dias só para achar acordos, sem pôr os processos deles na planilha. Padrão 0. Cada dia custa cerca de 134 MB e mais tempo de leitura.

## 7. O que muda na planilha

- `Pontuacao` passa a ter: acordo_anterior, imovel, transito, desgaste, veiculo, credor, descontos, total.
- Colunas de sinais: "Sinais de desgaste", "Sinais de patrimônio" (imóvel, veículo e acordo em outro processo) e "Alertas" (no lugar de vulnerabilidade, com os descontos e alertas). A aba Como ler e a seção de pontos são reescritas com a tabela da seção 5.
- As faixas de cor (verde ≥75, amarelo 50 a 74) ficam como estão *(escolha minha)*. Na prática, verde vai exigir acordo anterior ou imóvel com trânsito.
- O resumo do terminal ganha duas linhas: processos de banco tirados e processos com menos de 1 ano tirados.

## 8. Para quem construir

- TDD como no projeto: testes antes, com nomes fictícios (JOÃO EXEMPLO, BANCO EXEMPLO S.A.), sem rede.
- Testes obrigatórios: banco fora; caso com menos de 1 ano fora; acordo homologado no processo A pontua o processo B do mesmo devedor e não pontua o próprio A; homônimo de duas palavras não casa; frase de texto-padrão com "trânsito em julgado", se aparecer na primeira rodada real, não pontua.
- As frases exatas de acordo homologado e de trânsito em julgado devem ser conferidas na primeira rodada real, como foi feito com os textos-padrão em 08/11.
