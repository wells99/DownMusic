# Plano do projeto — downloader de áudio para CasaOS

## Objetivo

Transformar os scripts atuais em uma aplicação independente, executável com Docker e fácil de instalar no CasaOS, para baixar áudio de vídeos ou playlists do YouTube. A aplicação deve oferecer uma página web simples para informar a URL e definir metadados, respeitando pausas entre requisições e guardando os arquivos em uma pasta persistente escolhida pelo usuário.

O resultado esperado de cada download é somente o áudio em MP3, com metadados e capa quando disponíveis. O arquivo de vídeo intermediário não deve permanecer na pasta de destino.

## O que existe hoje

- `download.bat` usa `yt-dlp`, o cliente do YouTube `android`, extração MP3 em 192 kbps, inclusão de metadados e thumbnail, conversão da capa para JPG e pausas aleatórias de 15 a 45 segundos. O destino atual usa índice da playlist e título.
- `corrigir_artistas.py` altera a tag de artista ID3 (`TPE1`) para um valor fixado no código. `Helloween` é somente um exemplo antigo, não um valor padrão do novo app. Não altera o álbum.

- Os scripts dependem de `yt-dlp`, Python e `ffmpeg` instalados no ambiente em que são executados.

## Escopo proposto

### Interface web

- Campo obrigatório para URL de vídeo ou playlist.
- Campo de artista para gravar no metadado do MP3; inicialmente vazio, com valor padrão sugerido pelo usuário quando informado.
- Campo de álbum opcional, vazio por padrão. Se preenchido, gravá-lo no metadado; se omitido, deixar o álbum em branco/remover a tag herdada quando viável.
- Indicação do andamento e resultado, com mensagens de erro compreensíveis.
- Lista dos trabalhos recentes e acesso aos arquivos gerados.
- Ícone musical e apresentação simples, adaptada a celular e desktop.

### Download e processamento

- Usar `yt-dlp` com `ffmpeg` na imagem Docker para extrair/converter áudio para MP3 em 192 kbps.
- Preservar o argumento de extractor `youtube:player_client=android`, pois o script atual o usa por ser o comportamento que funcionou no ambiente do usuário. Confirmar compatibilidade com a versão de `yt-dlp` escolhida durante a implementação.
- Aplicar intervalo aleatório configurável ou fixo dentro de 5 a 45 segundos entre itens, cobrindo o processamento de playlists. Valor inicial proposto: mínimo 5 e máximo 45 segundos; avaliar na implementação como assegurar o intervalo entre requisições sem duplicar pausas internas do `yt-dlp`.
- Incluir metadados e thumbnail/capa quando disponíveis, convertendo a thumbnail para JPG se necessário.
- Após a conversão, manter somente o MP3 (e a capa incorporada, se suportada); remover arquivos intermediários de vídeo e temporários com tratamento de falhas.
- Aplicar artista e álbum solicitados ao MP3 final usando uma biblioteca de tags ID3, validando o resultado e tratando arquivos sem tags existentes.
- Permitir playlists e evitar colisões de nomes. Proposta inicial de saída: `%(uploader)s/%(playlist_index&{}|)s%(title)s.%(ext)s` ou equivalente validado para o `yt-dlp`; a implementação deve preservar a organização por uploader desejada sem gerar diretórios inválidos quando o uploader estiver ausente. O padrão atual `%(playlist_index)02d - %(title)s` pode ser oferecido como alternativa.

### Armazenamento e Docker/CasaOS

- Criar uma aplicação com serviço web e processamento em segundo plano, empacotada em Docker; incluir `yt-dlp`, `ffmpeg` e dependências Python necessárias na imagem.
- Persistir os downloads num diretório de dados montado como volume, em vez de depender da camada efêmera do container. Documentar o mapeamento de uma pasta do host/NAS para o diretório de saída do container, no estilo familiar do MeTube.
- Permitir configurar a pasta do host pelo mapeamento de volume do Docker/CasaOS; não permitir que a interface navegue livremente pelo sistema de arquivos do host.
- Fornecer configuração de implantação compatível com CasaOS (por exemplo, `docker-compose.yml` e instruções para instalação/atualização), porta web configurável e política de reinício adequada.
- Documentar permissões do diretório montado, atualização da imagem, backup e persistência após recriação do container.

## Diretrizes e decisões de implementação

- Manter a configuração fora do código: artista e álbum são informados por trabalho; pasta de saída é definida pelo volume/configuração do container.
- Não aceitar templates de saída arbitrários sem validação. Expor um template conhecido/configuração simples ou um conjunto de opções seguras para reduzir erros de caminho e sobrescrita acidental.
- Sanitizar nomes e impedir que títulos ou nomes de uploader escapem do diretório montado.
- Processar trabalhos em fila, com concorrência limitada (inicialmente um trabalho por vez), evitando downloads simultâneos inesperados.
- Mostrar claramente que baixar conteúdo deve respeitar direitos autorais, termos aplicáveis e permissões do usuário, sem tentar contornar controles de acesso.
- Não armazenar credenciais nem cookies na primeira versão.

## Decisões adotadas durante o desenvolvimento

- URL: aceitar vídeos e playlists do YouTube.
- Artista vazio: preservar o artista original; artista informado substitui a tag.
- Álbum vazio: remover a tag do álbum; preenchido substitui a tag.
- Saída: `uploader/título [id].mp3`; o ID evita colisões de títulos e uploader ausente usa `Unknown`.
- Histórico: manter no máximo 50 trabalhos recentes em memória; reiniciar o container limpa histórico, mas não os downloads no volume.
- Temporários: cada trabalho usa `.staging/<id>` e a pasta é removida ao concluir ou falhar.
- Fila: processamento único por vez, com limite de 50 trabalhos ativos e histórico recente em memória.
- Servidor web: Gunicorn com um worker para não dividir a fila entre processos; trabalhos ativos não são retomados depois de reinício.

## Checklist de execução

### 1. Definição e desenho

- [x] Confirmado: URLs de vídeo e playlists do YouTube.
- [x] Definido: campo de artista vazio preserva o metadado original; valor informado substitui a tag.
- [x] Definido: campo de álbum vazio remove a tag do álbum; valor informado substitui a tag.
- [x] Definido: pasta por uploader, arquivo por título e ID único; uploader ausente usa `Unknown`.
- [x] Definido: histórico em memória limitado aos últimos 50; pasta temporária por trabalho removida ao terminar.

### 2. Aplicação

- [x] Backend Flask com formulário, validação de host e campos de metadados.
- [x] Fila sequencial, estados, mensagens resumidas e histórico limitado a 50 trabalhos.
- [x] Integração `yt-dlp`: cliente `android`, MP3 192 kbps e pausa aleatória entre downloads de 5–45 segundos.
- [x] Docker instala `ffmpeg`; processamento configura conversão JPG e inclusão da thumbnail quando disponível.
- [x] Aplicação de tags ID3: artista informado substitui; vazio preserva. Álbum informado substitui; vazio remove.
- [x] Temporários são baixados numa pasta isolada removida após sucesso ou falha; MP3 final é movido ao volume persistente.
- [x] Caminhos confinados ao volume, saída por uploader/título/ID e sufixo em caso de colisão.
- [x] Página responsiva com ícone musical, formulário, estado dos trabalhos e lista de MP3s.
- [x] APIs para enfileirar e acompanhar trabalhos e listar/baixar arquivos MP3.

### 3. Docker e CasaOS

- [x] Dockerfile criado com Python, dependências fixadas e `ffmpeg`. `yt-dlp` fixado em 2026.10.26.
- [x] Compose criado com volume persistente, porta configurável e reinício automático.
- [x] Gunicorn configurado como servidor web do container; processo único preserva a fila em memória.
- [x] Limpeza de pastas temporárias abandonadas na inicialização do container.
- [ ] Testar permissões de leitura/escrita do volume com usuário não privilegiado, se viável.
- [x] README documenta instalação Compose, mapeamento de pasta, atualização e backup no CasaOS.
- [x] README lista variáveis e configuração padrão.
- [x] `.env.example` preparado com porta e caminho sugerido para a pasta persistente.

### 4. Verificação antes de publicar

- [ ] Verificar download de um vídeo autorizado e saída apenas em MP3.
- [ ] Verificar playlist com pausa entre itens e nomes de saída esperados.
- [ ] Conferir tags de artista e álbum no arquivo final, inclusive campos vazios.
- [ ] Conferir capa incorporada quando disponível e comportamento quando ausente.
- [ ] Confirmar que arquivos de vídeo e temporários não permanecem após sucesso e falha.
- [ ] Confirmar persistência dos downloads após reiniciar/recriar o container.
- [ ] Revisar logs, mensagens de erro, uso de recursos e comportamento ao reiniciar com trabalho pendente.
- [ ] Revisar documentação e fluxo de instalação no CasaOS.

## Fora do escopo inicial

- Contas de usuário, autenticação remota ou exposição direta à internet.
- Suporte a cookies, login, conteúdo privado ou outras formas de contornar restrições.
- Edição manual de capas e gerenciamento avançado de biblioteca musical.
- Execução simultânea de vários downloads.

## Critério de conclusão

A primeira versão estará pronta quando puder ser instalada no CasaOS via Docker, receber uma URL pela interface, baixar o áudio como MP3 com os metadados escolhidos e capa disponível, respeitar o intervalo definido, guardar o resultado no volume persistente escolhido e remover os vídeos/temporários do processamento.


