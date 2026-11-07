# DownMusic para CasaOS

Aplicação local para baixar áudio de vídeos ou playlists do YouTube como MP3, com campos opcionais para corrigir artista e álbum. A saída padrão segue `uploader/título [id].mp3`, com o ID do YouTube para evitar colisões entre títulos repetidos.

## Iniciar com Docker Compose

1. Instale Docker e Docker Compose no servidor CasaOS.
2. Copie esta pasta para o servidor ou clone o repositório.
3. Copie `.env.example` para `.env` ao lado do `docker-compose.yml` e ajuste a pasta persistente:

   ```env
   WEB_PORT=8080
   DOWNLOADS_PATH=/DATA/Media/DownMusic
   ```

   `DOWNLOADS_PATH` é uma pasta do host CasaOS. Ela será montada em `/downloads` no container; os MP3 continuarão disponíveis nessa pasta após atualizar ou recriar o container. A pasta precisa permitir escrita pelo UID `10001` usado pela aplicação. Crie a pasta e ajuste suas permissões no host antes de iniciar.

4. Inicie:

   ```sh
   docker compose up -d --build
   ```

5. Abra `http://IP_DO_CASAOS:8080` (ou a porta escolhida em `WEB_PORT`).

No catálogo de apps do CasaOS, também é possível criar um app personalizado usando a imagem construída com este Dockerfile, publicar a porta `8080` e mapear a pasta de destino desejada do host para `/downloads`.

## Uso

- Cole uma URL de vídeo ou playlist do YouTube.
- Informe artista se quiser substituir a tag original. Campo vazio preserva o artista existente.
- Informe álbum se quiser gravar a tag. Campo vazio remove a tag de álbum.
- Os itens da playlist são processados sequencialmente com pausa aleatória de 5 a 45 segundos antes dos downloads, qualidade MP3 de 192 kbps e cliente YouTube `android`.
- A capa é incorporada quando houver thumbnail adequada. Vídeos intermediários não são mantidos no diretório de downloads.
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
