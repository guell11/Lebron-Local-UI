
from huggingface_hub import hf_hub_download, snapshot_download
import os

JSPACE_REPO = "guell00/J-Space-Deliberation"
GEMMA_MODEL = "google/gemma-4-E4B-it"

FILES = [
    "jreasoner_config.json",
    "jspace_dictionary_v3.pt",
    "jacobian_lens.pt",
    "chat_template.jinja",
    "manifest.json",
    "tokenizer.json",
    "tokenizer_config.json",
]

OPTIONAL = [
    "jreasoner_adapter.pt"
]


def download_file(repo, filename, folder):
    print(f"Baixando: {filename}")

    hf_hub_download(
        repo_id=repo,
        filename=filename,
        local_dir=folder
    )

    print(f"OK: {filename}")


def setup_models():

    os.makedirs("models/J-Space-Deliberation", exist_ok=True)
    os.makedirs("models/Gemma-4-E4B-it", exist_ok=True)

    print("\n===== J-SPACE =====")

    for file in FILES:
        download_file(
            JSPACE_REPO,
            file,
            "models/J-Space-Deliberation"
        )

    print("\n===== ADAPTER OPCIONAL =====")

    for file in OPTIONAL:
        try:
            download_file(
                JSPACE_REPO,
                file,
                "models/J-Space-Deliberation"
            )
        except Exception:
            print("Adapter não encontrado. Continuando.")

    print("\n===== GEMMA 4 E4B =====")
    print("Baixando modelo base...")

    snapshot_download(
        repo_id=GEMMA_MODEL,
        local_dir="models/Gemma-4-E4B-it"
    )

    print("\nTodos os arquivos foram preparados.")
