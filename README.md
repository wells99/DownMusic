# DownMusic para CasaOS

Aplicação local para baixar áudio de vídeos ou playlists do YouTube como MP3, com campos para escolher a pasta e opções para corrigir artista e álbum. Os itens do trabalho ficam juntos em `pasta escolhida/título.mp3`; só títulos repetidos recebem um sufixo numérico para evitar sobrescrita.

## Iniciar com Docker Compose

1. Instale Docker e Docker Compose no servidor CasaOS.
2. Copie esta pasta para o servidor ou clone o repositório.
3. Copie `.env.example` para `.env` ao lado do `docker-compose.yml` e ajuste a pasta persistente:

   ```env
   WEB_PORT=8080
   DOWNLOADS_PATH=/DATA/Media/DownMusic
   ```

   `DOWNLOADS_PATH` é uma pasta do host CasaOS. Ela será montada em `/downloads` no container; os MP3 continuarão disponíveis nessa pasta após atualizar ou recriar o container. A pasta precisa permitir escrita pelo UID `10001` usado pela aplicação. Crie a pasta e ajuste suas permissões no host antes de iniciar.

4. No terminal do CasaOS, entre na pasta que contém o `Dockerfile` e o `docker-compose.yml` e execute:

   ```sh
   docker compose up -d --build
   docker compose ps -a
   ```

5. Abra `http://IP_DO_CASAOS:8080` (ou a porta escolhida em `WEB_PORT`).

O Compose constrói a imagem local `downmusic:latest` a partir do `Dockerfile`. A configuração declara `downmusic` como imagem e `latest` como tag para o CasaOS. Se você já tinha criado o contêiner com o Compose anterior, execute o passo 4 na mesma pasta para recriá-lo com a imagem nomeada.

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
