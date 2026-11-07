from pathlib import Path
import shutil

from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TPE1

# Pasta atual onde o script está rodando
PASTA = Path.cwd()

# Novo valor do campo de Artista
ARTISTA = "Helloween"

# O comando .glob("*.mp3") pega apenas os arquivos da pasta atual
arquivos = list(PASTA.glob("*.mp3"))

if not arquivos:
    print("Nenhum arquivo MP3 encontrado na pasta atual.")
    raise SystemExit(0)

for arquivo in arquivos:
    try:
        # Criar backup antes de alterar (evita perda de dados em caso de erro no meio do processo)
        backup = arquivo.with_suffix(arquivo.suffix + ".bak")

        if not backup.exists():
            shutil.copy2(arquivo, backup)

        # Abrir o MP3 e carregar suas tags ID3
        audio = MP3(arquivo, ID3=ID3)

        if audio.tags is None:
            audio.add_tags()

        # Atualizar o artista principal/participante (TPE1)
        audio.tags.delall("TPE1")
        audio.tags.add(
            TPE1(encoding=3, text=[ARTISTA])
        )

        audio.save()

        print(f"OK: {arquivo.name}")

    except Exception as erro:
        print(f"ERRO: {arquivo.name}: {erro}")

print(f"\nProcessamento concluído: {len(arquivos)} arquivo(s).")

# --- NOVA PARTE: Limpar arquivos de backup (.bak) ---
arquivos_bak = list(PASTA.glob("*.bak"))
for bak in arquivos_bak:
    try:
        bak.unlink() # Comando que deleta o arquivo
    except Exception as erro:
        print(f"Erro ao deletar o backup {bak.name}: {erro}")

print(f"{len(arquivos_bak)} arquivo(s) de backup (.bak) apagado(s) com sucesso!")