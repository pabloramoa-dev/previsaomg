# Comunicados em dupla (Bira + Bia)

Reel avulso, feito só quando você pedir, com os dois personagens conversando no
mesmo estúdio dos Reels diários. Serve para três coisas:

| `tipo` | Para quê | Música |
| --- | --- | --- |
| `alerta` | tempestade, granizo, vendaval, calor forte, frio, virada brusca | sem trilha (só efeitos) |
| `evento` | agenda do fim de semana, show, festival, divulgação de parceiro | trilha com ducking |
| `lembrete` / `aviso` | campanha, prazo, data importante, recado do canal | trilha com ducking |

## Como usar

1. Copie um dos exemplos (`exemplo_alerta.yaml`, `exemplo_evento.yaml`,
   `exemplo_lembrete.yaml`) com um nome novo, por exemplo
   `comunicados/alerta_2026-11-18.yaml`, e troque os dados.
2. No GitHub: **Actions → Comunicado em dupla → Run workflow**, informe o
   arquivo e deixe **publicar** desmarcado para receber só o vídeo.
3. Conferiu o vídeo? Rode de novo com **publicar** marcado.

## Campos

```yaml
tipo: alerta            # alerta | evento | lembrete | aviso
apresenta: bia          # quem abre e faz o CTA; o outro acompanha
validade: "2026-11-18T23:59"   # depois disso o roteiro não roda mais
titulo: "ALERTA DE TEMPESTADE" # título grande da abertura
etiquetas: ["AVISO DO INMET", "HOJE · ATÉ 23H59"]   # duas etiquetas da abertura
selo: "ALERTA"          # opcional: etiqueta do HUD (padrão pelo tipo)
ceu: tempestade         # opcional: sol, calor, nublado, chuva, tempestade, frio
trilha: false           # opcional: liga/desliga a música
fonte: "INMET — aviso amarelo"  # vai no fim da legenda
ticker: ["CHUVA ATÉ 30 MM/H", "DEFESA CIVIL 199"]   # faixa de baixo
falas:                  # 1ª = abertura, última = cta
  - cena: abertura
    fala: "Atenção! ..."
  - cena: alerta        # placa vermelha: titulo + detalhe
  - cena: numero        # número grande: numero + sub + local (icone: vento)
  - cena: cartaz        # cartão de evento: rotulo, nome, quando, onde, detalhe, selo
  - cena: frase         # frase na tela (continua: true junta com a anterior)
  - cena: cta           # chamada + sub, com figurantes e card "Seguir"
legenda: |
  Texto da publicação. Precisa citar {arroba}.
```

- As falas alternam sozinhas entre quem apresenta e quem acompanha; use
  `quem: bia` ou `quem: bira` para forçar.
- `{arroba}`, `{marca}` e `{curto}` viram a identidade do canal
  (`config/estado.yaml`).
- **Alertas:** só números de fonte oficial (INMET, Defesa Civil, Cemaden) e
  sempre com `validade`. Nunca afirme granizo sem aviso oficial.
- **Eventos:** confira data, horário, local e preço na página oficial do
  evento antes de publicar.

Teste local (sem publicar):

```bash
python hyperframes/comunicado_dupla.py comunicados/exemplo_alerta.yaml --so-validar --ignorar-validade
python hyperframes/comunicado_dupla.py comunicados/exemplo_evento.yaml --ignorar-validade --out output/teste.mp4
```

Recursos gratuitos usados (em `hyperframes/assets/dupla/`): SFX Kit
(github.com/wyzowl/sfx-kit, CC0), "Sunset on the Beach" de Komiku (CC0),
figurantes Open Peeps (Pablo Stanley, CC0, via DiceBear) e geopattern (MIT).
