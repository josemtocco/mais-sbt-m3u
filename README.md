# +SBT — Gerador M3U automático

Gerador de playlist M3U para os canais ao vivo do **+SBT**:

https://mais.sbt.com.br/

O projeto foi feito para não depender apenas dos links existentes no HTML inicial. O site é dinâmico, portanto o gerador:

- abre o +SBT com Chromium;
- procura links `/channel/` em HTML, scripts e JSON;
- monitora requisições e respostas da rede;
- procura manifestos HLS `.m3u8`;
- procura URLs de CDN usadas pelo player;
- tenta iniciar os players das páginas encontradas;
- identifica nome e categoria;
- testa cada stream com FFmpeg;
- remove automaticamente streams que falharem;
- gera `mais-sbt.m3u` diretamente na raiz;
- grava `descoberto.json` para diagnóstico;
- atualiza automaticamente pelo GitHub Actions.

## Estrutura

```text
mais-sbt-m3u/
├── .github/
│   └── workflows/
│       └── atualizar.yml
├── mais-sbt.m3u
├── descoberto.json
├── gerar_m3u.py
├── requirements.txt
└── README.md
```

## Instalação local

```bash
pip install -r requirements.txt
playwright install chromium
```

Também é necessário FFmpeg/ffprobe.

```bash
python gerar_m3u.py
```

## Arquivos de saída

### Playlist

```text
mais-sbt.m3u
```

### Diagnóstico

```text
descoberto.json
```

O diagnóstico informa:
- páginas de canais descobertas;
- streams encontrados;
- streams testados;
- streams aprovados;
- erros.

Isso evita que uma execução silenciosamente gere uma playlist vazia.

## GitHub Actions

O workflow roda a cada 6 horas e também pode ser executado manualmente:

**GitHub → Actions → Atualizar lista +SBT → Run workflow**

A lista ficará disponível em:

```text
https://raw.githubusercontent.com/josemtocco/SEU-REPOSITORIO/main/mais-sbt.m3u
```

Substitua `SEU-REPOSITORIO` pelo nome do seu repositório.

## Observação

O gerador captura somente manifestos de reprodução disponibilizados pelo próprio site/player. Ele não tenta quebrar DRM ou contornar autenticação.
