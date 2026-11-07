# DownMusic

Aplicação local para baixar áudio de vídeos ou playlists do YouTube como MP3, com campos para escolher a pasta e opções para corrigir artista e álbum. Os itens do trabalho ficam juntos em `pasta escolhida/título.mp3`; só títulos repetidos recebem um sufixo numérico para evitar sobrescrita.

## Iniciar com Docker Compose

1. Com o Docker e o Docker Compose instalados, abra o terminal na pasta do projeto.
2. Para salvar os MP3 em `./download`, copie `.env.example` para `.env` ao lado do `docker-compose.yml` e use esta configuração.

   ```env
   WEB_PORT=8080
   DOWNLOADS_PATH=./download
   ```

3. Crie a pasta `download` na raiz do projeto. No Linux, ela precisa permitir escrita pelo UID `10001`, usado pelo contêiner. Para uma pasta recém-criada, use `sudo chown 10001 ./download`.

4. Construa a imagem e inicie o contêiner.

   ```sh
   docker compose up -d --build
   docker compose ps
   ```

5. Abra `http://localhost:8080` ou use a porta definida em `WEB_PORT`.

O Compose monta a pasta indicada em `DOWNLOADS_PATH` como `/downloads` no contêiner. Os MP3 ficam na pasta do host mesmo após recriar o contêiner.

## Uso

- Cole uma URL de vídeo ou playlist do YouTube.
- Informe artista se quiser substituir a tag original. Campo vazio preserva o artista existente.
- Informe álbum se quiser gravar a tag. Campo vazio remove a tag de álbum.
- Escolha o nome da pasta onde os MP3 serão salvos. Os itens de uma playlist vão todos para a mesma pasta, mesmo quando são de canais diferentes.
- Ajuste a pausa mínima e máxima entre itens de playlist (5–45 segundos). A página mostra a contagem regressiva da pausa escolhida; vídeos individuais não precisam de espera entre itens.
- Os downloads são processados sequencialmente em MP3 de 192 kbps, usando o cliente YouTube `android`.
- A capa é incorporada quando houver thumbnail adequada. Vídeos intermediários não são mantidos no diretório de downloads.
- Avisos rotineiros do `yt-dlp` ficam ocultos na página; em caso de falha, a página mostra o resumo e os detalhes do erro. A tag de número/faixa ID3 (`TRCK`) é removida.
- Os trabalhos e mensagens recentes ficam em memória (até 50; reiniciar o container limpa o histórico). Os MP3 ficam no volume persistente.

Use somente para conteúdos que você tem direito de baixar e armazenar. Esta primeira versão não usa cookies nem autenticação e deve ficar restrita à rede local.

## Configuração

| Variável | Padrão | Uso |
|---|---:|---|
| `WEB_PORT` | `8080` | Porta publicada no host pelo Compose |
| `DOWNLOADS_PATH` | `./downloads` | Pasta persistente no host |
| `DOWNLOAD_DIR` | `/downloads` | Caminho do volume dentro do container |
| `PORT` | `8080` | Porta interna do servidor web |

A fila executa um download por vez e aceita até 50 trabalhos pendentes/ativos. O servidor web usa Gunicorn com um processo para manter a fila única. Se o container reiniciar durante um download, o trabalho interrompido não é retomado; a pasta temporária abandonada é limpa na inicialização. Para atualizar a aplicação, atualize os arquivos e execute `docker compose up -d --build`. Faça backup da pasta apontada por `DOWNLOADS_PATH`.
