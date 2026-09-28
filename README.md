# Gerador M3U — +SBT

Projeto para gerar automaticamente uma playlist M3U dos canais ao vivo disponíveis em:

https://mais.sbt.com.br/

Características:
- descoberta automática das páginas de canais;
- captura dos streams HLS `.m3u8` carregados pelo +SBT;
- nome do canal;
- categoria;
- `tvg-name`;
- idioma `pt-BR`;
- país `BR`;
- teste dos streams antes de entrar na playlist;
- remoção automática de streams que falharem;
- atualização automática pelo GitHub Actions;
- saída em `mais-sbt.m3u`.

## Estrutura

```text
mais-sbt-m3u/
├── .github/
│   └── workflows/
│       └── atualizar.yml
├── mais-sbt.m3u
├── gerar_m3u.py
├── requirements.txt
└── README.md
```

## Como instalar

```bash
pip install -r requirements.txt
playwright install chromium
```

Para testar localmente:

```bash
python gerar_m3u.py
```

## GitHub

O workflow executa automaticamente 2 vezes por dia e também pode ser iniciado manualmente em:

**GitHub → Actions → Atualizar lista +SBT → Run workflow**

A playlist publicada ficará em:

```text
https://raw.githubusercontent.com/SEU_USUARIO/SEU_REPOSITORIO/main/playlist/mais-sbt.m3u
```

Substitua `SEU_USUARIO/SEU_REPOSITORIO` pelos dados do seu repositório.

## Observação

O site +SBT é dinâmico. Por isso o projeto usa navegador automatizado para descobrir os streams atuais em vez de depender de uma lista fixa de URLs.
