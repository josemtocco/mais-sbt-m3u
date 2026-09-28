# +SBT M3U — v3

Gerador de playlist dos canais ao vivo do +SBT.

O catálogo atual do +SBT é usado como referência. Como a página oficial entrega os dados do player dinamicamente e não expõe os canais no HTML inicial para crawlers, o projeto usa uma segunda camada de descoberta de streams públicos.

Canais de referência:
- SBT
- SBT Rio
- SBT News
- +SBT Novelas
- Canal Show do Milhão
- SBT Kids

A playlist só publica um canal quando o stream correspondente passa pelo teste `ffprobe`.

## Estrutura

```text
mais-sbt-m3u/
├── .github/
│   └── workflows/
│       └── atualizar.yml
├── mais-sbt.m3u
├── descoberto.json
├── gerar_m3u.py
├── fontes.json
├── requirements.txt
└── README.md
```

## Importante

Esta versão não depende exclusivamente do HTML do `mais.sbt.com.br`.

Ela consulta:
1. catálogo atual do +SBT;
2. fontes públicas de M3U/HLS usadas como fallback de descoberta;
3. teste individual dos streams.

Isso é necessário porque a página oficial do +SBT é dinâmica e o crawler pode receber apenas um conteúdo mínimo.

Os streams não são inventados. URLs entram na playlist somente depois de serem encontradas em fontes públicas configuradas e aprovadas no teste.

## GitHub

Envie os arquivos para o repositório e execute:

**Actions → Atualizar lista +SBT → Run workflow**

A atualização automática acontece a cada 6 horas.

Playlist:

```text
https://raw.githubusercontent.com/josemtocco/SEU-REPOSITORIO/main/mais-sbt.m3u
```

Diagnóstico:

```text
descoberto.json
```

O diagnóstico mostra encontrados, aprovados e rejeitados.
