# Previsão MG — @previsaomg

Reels automáticos de previsão do tempo em Minas: **Bira do Tempo** às
06:00 com a previsão de hoje e **Bia** às 18:00 com a de
amanhã (hora local, UTC-3; 06:00 e 18:00 em Brasília).

Gerado de `pabloramoa-dev/previsao-modelo` por `scripts/novo_estado.py`. Motor, personagens,
vozes e testes são os do modelo; o que é deste canal está em `config/estado.yaml` e
`config/locais.yaml`. Correção no motor se faz no modelo e se propaga.

Dados: [MET Norway](https://api.met.no) (licença CC BY 4.0, crédito em toda legenda).

## Quadro das oito regiões

| Região | Primeira cidade | Outras cidades do rodízio |
| --- | --- | --- |
| Grande BH | Belo Horizonte | Contagem, Betim |
| Triângulo | Uberlândia | Uberaba, Araguari |
| Zona da Mata | Juiz de Fora | Viçosa, Muriaé |
| Sul de Minas | Poços de Caldas | Varginha, Pouso Alegre |
| Norte | Montes Claros | Janaúba, Pirapora |
| Vale do Rio Doce | Governador Valadares | Ipatinga, Caratinga |
| Jequitinhonha e Mucuri | Teófilo Otoni | Araçuaí, Diamantina |
| Centro-Oeste e Alto Paranaíba | Divinópolis | Patos de Minas, Araxá |

## Colocar no ar

1. Settings → Actions → General → Workflow permissions: **Read and write**.
2. Settings → Secrets and variables → Actions → **Variables**:
   `AUTOMATION_ENABLED=false`, `EXPECTED_IG_USERNAME=previsaomg`.
3. Rodar **CI**, **Coletar dados (sem publicação)** e **Validar estúdio HyperFrames**. Para ensaiar, usar **Reel manual** com publicação desmarcada;
   assistir aos dois MP4 (nomes, preposições, cenário, sigla).
4. Conta @previsaomg profissional + app da Meta ("API do Instagram com login do
   Instagram", escopos `instagram_business_basic`, `instagram_business_content_publish`,
   `instagram_business_manage_insights`).
5. **Secrets**: `IG_USER_ID`, `IG_ACCESS_TOKEN`, `GH_PAT_SECRETS` (fine-grained, só este
   repo, Secrets: write).
6. **Health — conexão com a Meta** → `verified` com @previsaomg.
7. **Reel manual** em modo live, com publicação desmarcada, para validar a coleta e revisar o vídeo.
8. **Token — renovar IG** uma vez à mão; depois roda sozinho nos dias 1 e 15.
9. `AUTOMATION_ENABLED=true`.
10. Opcionalmente, adicionar cron-job.org como disparador redundante. Usar fuso `America/Sao_Paulo`, POST
    `https://api.github.com/repos/pabloramoa-dev/previsaomg/dispatches`:
    `{"event_type":"reel_manha"}` às 05:35 e `{"event_type":"reel_noite"}` às 17:35.

## Rodízio e monitoramento

O cartão mostra uma sede por região. O dia da previsão escolhe a cidade inicial
da lista de cada região e a coleta consulta as três sedes. A chamada final usa
o maior acumulado entre os pontos com dados válidos. Coordenadas das 24 sedes
conferidas no [cadastro de localidades do IBGE, Censo 2022](https://www.ibge.gov.br/geociencias/organizacao-do-territorio/estrutura-territorial/27385-localidades).

O monitor consulta os avisos CAP do INMET às 11h de Brasília e guarda evidências
com município, tipo, validade e fonte. Se a consulta falhar, a execução falha
sem converter indisponibilidade em indicação de tempo seguro. A automação de
envio dos avisos ao Instagram depende da integração do novo canal.
