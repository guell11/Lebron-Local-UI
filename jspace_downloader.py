from huggingface_hub import hf_hub_download
import os

REPO = "guell00/J-Space-Deliberation"

FILES = [
    "jreasoner_config.json",
    "jspace_dictionary_v3.pt",
    "jacobian_lens.pt",
    "chat_template.jinja",
    "manifest.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "jreasoner_adapter.pt"
]

def download_jspace():
    folder = "models/J-Space-Deliberation"
    os.makedirs(folder, exist_ok=True)

    for file in FILES:
        try:
            print("Downloading:", file)
            hf_hub_download(repo_id=REPO, filename=file, local_dir=folder)
            print("OK:", file)
        except Exception as e:
            print("Skipped:", file, e)

if __name__ == "__main__":
    download_jspace()
